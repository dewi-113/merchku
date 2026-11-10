"""Jawaban CS memakai Claude (opsional).

Aktif hanya bila paket `anthropic` terpasang dan ANTHROPIC_API_KEY diisi.
Jika tidak aktif, gagal, atau permintaan ditolak, fungsi ini mengembalikan
None dan route memakai mesin jawaban otomatis (engine.py).
"""
import logging
import os

from flask import current_app

from app.cs.knowledge import STATUS_LABELS, STORE_FACTS

log = logging.getLogger(__name__)

DEFAULT_MODEL = 'claude-haiku-5-5'

PERSONA = """\
Kamu adalah "Merchy", customer service Merchku Store. Jawab dalam bahasa Indonesia yang
ramah, santai, dan singkat (maksimal sekitar 5 kalimat atau 6 poin), boleh 1 emoji.
Gunakan teks biasa: boleh memakai "•" untuk daftar, jangan memakai format markdown
seperti **tebal** atau judul.

Aturan:
- Jawab hanya hal yang berkaitan dengan belanja di Merchku Store. Tolak dengan sopan topik lain.
- Gunakan HANYA fakta toko dan katalog di bawah. Jangan mengarang kebijakan, promo,
  voucher, harga, stok, nomor kontak, atau estimasi waktu yang tidak tertulis.
  Jika tidak tahu, katakan terus terang dan sarankan chat penjual atau admin.
- Sebut nama produk persis seperti di katalog; kartu produk akan ditampilkan otomatis.
- Data pesanan pengguna (jika ada) diberikan sistem dalam percakapan; jangan pernah
  membahas pesanan milik orang lain.
"""


def is_enabled():
    if not os.getenv('ANTHROPIC_API_KEY'):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def _catalog_text():
    from app.katalog.models import Product

    lines = []
    products = (
        Product.query.filter_by(is_active=True)
        .order_by(Product.category, Product.name).limit(150).all()
    )
    for p in products:
        price = f'Rp{p.price:,}'.replace(',', '.')
        if p.discount_percent:
            price += f' (diskon {p.discount_percent}% dari Rp{p.original_price:,})'.replace(',', '.')
        shop = p.owner.shop_name if p.owner and p.owner.shop_name else 'Merchku Store'
        sizes = ' | ukuran S-XXL' if p.use_sizes else ''
        lines.append(f'- {p.name} | {p.category} | {price} | stok {p.total_stock}{sizes} | toko {shop}')
    return 'KATALOG PRODUK AKTIF\n' + '\n'.join(lines)


def _user_context(user):
    from app.pesanan.models import Order

    if not (user and getattr(user, 'is_authenticated', False)):
        return 'Pengguna belum login.'
    name = getattr(user, 'recipient_name', None) or user.email.split('@')[0]
    if user.role != 'customer':
        return f'Pengguna login sebagai {user.role} bernama {name}.'
    orders = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(5).all()
    if not orders:
        return f'Pengguna login sebagai pembeli bernama {name}, belum punya pesanan.'
    rows = [
        f'#{o.id}: {STATUS_LABELS.get(o.status, o.status)}, total Rp{o.total_price:,}'.replace(',', '.')
        for o in orders
    ]
    return f'Pengguna login sebagai pembeli bernama {name}. Pesanan terbarunya: ' + '; '.join(rows)


def _clean_history(history):
    """Ambil maksimal 8 giliran terakhir, peran bergantian, diawali user."""
    cleaned = []
    for item in (history or [])[-8:]:
        role = item.get('role') if isinstance(item, dict) else None
        text = str(item.get('text') or '')[:1000].strip() if isinstance(item, dict) else ''
        if role not in ('user', 'assistant') or not text:
            continue
        if cleaned and cleaned[-1]['role'] == role:
            cleaned[-1]['content'] += '\n' + text
        else:
            cleaned.append({'role': role, 'content': text})
    while cleaned and cleaned[0]['role'] != 'user':
        cleaned.pop(0)
    if cleaned and cleaned[-1]['role'] == 'user':
        cleaned.pop()  # pesan user terbaru ditambahkan terpisah
    return cleaned


def ai_reply(message, history, user):
    """Kembalikan teks jawaban Claude, atau None bila tidak tersedia."""
    if not is_enabled():
        return None
    import anthropic

    # Default Haiku: model paling hemat, cukup untuk CS berbasis fakta toko.
    model = current_app.config.get('CS_AI_MODEL') or DEFAULT_MODEL
    messages = [*_clean_history(history), {
        'role': 'user',
        'content': [
            # Konteks pengguna dibuat server, ditaruh sebelum pesan pengguna agar
            # system prompt + katalog (yang di-cache) tetap sama di setiap request.
            {'type': 'text', 'text': f'<system-reminder>{_user_context(user)}</system-reminder>'},
            {'type': 'text', 'text': message[:1000]},
        ],
    }]
    extra = {}
    if model.startswith('claude-haiku-5'):
        # Jawaban CS pendek: matikan thinking agar token output tidak terpakai untuk berpikir.
        extra['thinking'] = {'type': 'disabled'}
    try:
        client = anthropic.Anthropic()
        response = client.with_options(timeout=25.0, max_retries=1).messages.create(
            model=model,
            max_tokens=1024,
            system=[
                {'type': 'text', 'text': PERSONA + '\n' + STORE_FACTS},
                {'type': 'text', 'text': _catalog_text(), 'cache_control': {'type': 'ephemeral'}},
            ],
            messages=messages,
            output_config={'effort': 'low'},
            **extra,
        )
    except anthropic.RateLimitError:
        log.warning('cs_ai rate limited')
        return None
    except anthropic.APIStatusError as exc:
        log.warning('cs_ai api error %s: %s', exc.status_code, exc.message)
        return None
    except anthropic.APIConnectionError:
        log.warning('cs_ai connection error')
        return None

    if response.stop_reason == 'refusal':
        return None
    text = '\n'.join(block.text for block in response.content if block.type == 'text').strip()
    return text or None
