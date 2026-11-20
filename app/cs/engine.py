"""Mesin jawaban otomatis Customer Service Merchku.

Bekerja tanpa layanan luar: mengenali maksud pertanyaan (intent) dengan kata
kunci, lalu menjawab memakai data toko yang asli (produk, stok, diskon,
terlaris, pesanan milik pengguna). Dipakai langsung, atau sebagai pelengkap
(kartu produk & tautan) saat jawaban teks dibuat oleh Claude.
"""
import re

from flask import url_for

from app import db
from app.cs.knowledge import COURIERS, SIZE_CHART, STATUS_LABELS

DEFAULT_SUGGESTIONS = ['Cara belanja', 'Cek status pesanan', 'Produk diskon', 'Metode pembayaran']

STOPWORDS = {
    'ada', 'apa', 'apakah', 'aku', 'saya', 'gue', 'gw', 'kak', 'kakak', 'min', 'admin', 'mau', 'ingin',
    'cari', 'carikan', 'beli', 'jual', 'yang', 'yg', 'dong', 'donk', 'ya', 'yah', 'gak', 'ga', 'nggak',
    'tidak', 'bisa', 'boleh', 'minta', 'tolong', 'berapa', 'harga', 'harganya', 'stok', 'stoknya',
    'masih', 'untuk', 'buat', 'dan', 'atau', 'di', 'ke', 'dari', 'ini', 'itu', 'nya', 'deh', 'sih',
    'kah', 'nih', 'tuh', 'produk', 'barang', 'merch', 'merchku', 'halo', 'hai', 'tersedia', 'warna',
    'ukuran', 'size', 'murah', 'bagus', 'rekomendasi', 'punya', 'kalian', 'kamu', 'lagi', 'the', 'pls',
}

# Kata sehari-hari → kata kunci produk di katalog
SYNONYMS = {
    'baju': 'kaos', 'tshirt': 'kaos', 't-shirt': 'kaos', 'kaus': 'kaos', 'sweater': 'hoodie',
    'hodie': 'hoodie', 'jacket': 'jaket', 'jas': 'almet', 'almamater': 'almet', 'tas': 'tote',
    'totebag': 'tote', 'cap': 'topi', 'gelas': 'mug', 'cangkir': 'mug', 'buku': 'notebook',
    'sticker': 'stiker', 'tali': 'lanyard', 'idcard': 'lanyard', 'keychain': 'gantungan', 'bros': 'pin',
}

INTENTS = [
    ('greeting', r'^(halo|hai|hi|hello|hey|pagi|siang|sore|malam|assalam|permisi|p+)\b'),
    ('thanks', r'\b(makasih|terima ?kasih|thanks|thank you|thx|tq|mantap|oke+ makasih)\b'),
    ('how_to_buy', r'\b(cara (beli|belanja|pesan|order|checkout)|gimana (beli|pesan|order)|checkout|keranjang)\b'),
    ('order_status', r'\b(status|lacak|tracking|resi|pesanan ?(ku|saya)?|orderan|order|sudah sampai|belum sampai|kapan sampai|dikirim)\b'),
    ('cancel', r'\b(batal|batalkan|membatalkan|cancel)\b'),
    ('refund', r'\b(retur|return|refund|kembalikan|pengembalian|uang kembali|rusak|cacat|salah kirim|komplain|complain|kecewa)\b'),
    ('payment', r'\b(bayar|pembayaran|transfer|tf|qris|cod|e-?wallet|gopay|ovo|dana|shopeepay|bukti bayar|rekening|midtrans)\b'),
    ('shipping', r'\b(ongkir|ongkos kirim|kirim|pengiriman|kurir|ekspedisi|jne|j&t|jnt|sicepat|anteraja|pos indonesia|berapa lama|estimasi)\b'),
    ('size', r'\b(ukuran|size|lingkar|lebar|panjang badan|cm|size ?chart|fit)\b'),
    ('discount', r'\b(diskon|promo|sale|potongan|voucher|hemat|flash)\b'),
    ('bestseller', r'\b(terlaris|laris|best ?seller|populer|paling banyak|favorit|rekomendasi|rekomen)\b'),
    ('account', r'\b(password|kata sandi|lupa|akun|login|masuk|daftar|register|email)\b'),
    ('seller', r'\b(jualan|berjualan|buka toko|jadi penjual|seller|mitra|titip jual)\b'),
    ('review', r'\b(ulasan|review|rating|bintang|nilai)\b'),
    ('human', r'\b(cs manusia|orang asli|admin asli|hubungi|kontak|contact|whatsapp|wa|telepon|chat penjual|chat seller)\b'),
]


def _rp(value):
    return 'Rp' + f'{value:,}'.replace(',', '.')


def product_payload(product):
    image = (
        url_for('core.produk_media', filename=product.image)
        if product.image else url_for('core.produk_foto', product_id=product.id)
    )
    return {
        'id': product.id,
        'name': product.name,
        'price': _rp(product.price),
        'old_price': _rp(product.original_price) if product.discount_percent else None,
        'discount': product.discount_percent,
        'stock': product.total_stock,
        'shop': product.owner.shop_name if product.owner and product.owner.shop_name else 'Merchku',
        'url': url_for('katalog.detail', pid=product.id),
        'image': image,
    }


def search_products(text, limit=4):
    """Cari produk aktif berdasarkan kata kunci dalam kalimat bebas."""
    from app.katalog.models import Product

    words = re.findall(r'[a-z0-9&-]+', text.lower())
    keywords = []
    for word in words:
        word = SYNONYMS.get(word, word)
        if len(word) >= 3 and word not in STOPWORDS and word not in keywords:
            keywords.append(word)
    if not keywords:
        return []
    candidates = Product.query.filter(
        Product.is_active.is_(True),
        db.or_(*[
            db.or_(Product.name.ilike(f'%{kw}%'), Product.category.ilike(f'%{kw}%'))
            for kw in keywords
        ]),
    ).limit(60).all()

    def score(product):
        haystack = f'{product.name} {product.category} {product.color or ""}'.lower()
        return (sum(kw in haystack for kw in keywords), product.total_stock > 0)

    candidates.sort(key=score, reverse=True)
    best = score(candidates[0])[0] if candidates else 0
    return [p for p in candidates if score(p)[0] == best][:limit]


def _detect_intent(text):
    for name, pattern in INTENTS:
        if re.search(pattern, text):
            return name
    return None


def _orders_for(user, text):
    from app.pesanan.models import Order

    match = re.search(r'#?\b(\d{1,7})\b', text)
    if match:
        order = db.session.get(Order, int(match.group(1)))
        if order and order.user_id == user.id:
            return [order]
    return Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).limit(3).all()


def answer(message, user=None):
    """Kembalikan dict: reply, products, links, suggestions, intent."""
    from app.katalog.models import Product
    from app.katalog.stats import best_seller_ids

    text = ' '.join((message or '').lower().split())
    logged_in = bool(user and getattr(user, 'is_authenticated', False))
    is_customer = logged_in and user.role == 'customer'
    intent = _detect_intent(text)
    links, products = [], []
    suggestions = DEFAULT_SUGGESTIONS

    if intent == 'greeting':
        name = ''
        if logged_in:
            name = ' ' + (getattr(user, 'recipient_name', None) or user.email.split('@')[0]).split()[0]
        reply = (
            f'Halo{name}! Aku Merchy, CS Merchku. Aku bisa bantu cari produk, cek status '
            'pesanan, info ongkir, pembayaran, sampai panduan ukuran. Mau tanya apa?'
        )
    elif intent == 'thanks':
        reply = 'Sama-sama! Kalau ada yang mau ditanyakan lagi, tinggal ketik aja ya.'
        suggestions = ['Produk terlaris', 'Produk diskon']
    elif intent == 'order_status':
        if not logged_in:
            reply = 'Untuk cek status pesanan, masuk dulu ke akunmu ya. Setelah itu tanya aku lagi atau buka menu Pesanan Saya.'
            links = [{'label': 'Masuk', 'url': url_for('auth.login', next=url_for('pesanan.riwayat'))}]
        elif not is_customer:
            reply = 'Fitur cek pesanan ini untuk akun pembeli. Penjual bisa melihat pesanan masuk di Dashboard Penjual.'
            links = [{'label': 'Pesanan masuk', 'url': url_for('seller.pesanan_list')}]
        else:
            orders = _orders_for(user, text)
            if not orders:
                reply = 'Kamu belum punya pesanan. Yuk mulai belanja!'
                links = [{'label': 'Jelajahi katalog', 'url': url_for('katalog.index')}]
            else:
                lines = ['Ini pesanan terbarumu:']
                for order in orders:
                    lines.append(
                        f'• Pesanan #{order.id} — {STATUS_LABELS.get(order.status, order.status)} '
                        f'({_rp(order.total_price)})'
                    )
                    links.append({'label': f'Detail #{order.id}', 'url': url_for('pesanan.detail', order_id=order.id)})
                pending = [o for o in orders if o.status in ('menunggu_pembayaran', 'ditolak')]
                if pending:
                    lines.append('Pesanan yang menunggu pembayaran bisa dibayar/unggah bukti dari halaman detailnya.')
                reply = '\n'.join(lines)
            suggestions = ['Cara bayar', 'Batalkan pesanan', 'Berapa lama pengiriman?']
    elif intent == 'cancel':
        reply = (
            'Pesanan bisa kamu batalkan sendiri selama statusnya "Menunggu pembayaran" atau '
            '"Bukti bayar ditolak": buka Pesanan Saya → pilih pesanan → Batalkan. Kalau sudah '
            'dibayar/dikirim, hubungi penjual lewat chat ya.'
        )
        links = [{'label': 'Pesanan Saya', 'url': url_for('pesanan.riwayat')}]
    elif intent == 'refund':
        reply = (
            'Maaf atas ketidaknyamanannya. Saat ini belum ada fitur retur/refund otomatis. '
            'Silakan chat penjualnya langsung dan sertakan nomor pesanan serta foto barang, '
            'supaya bisa ditindaklanjuti. Kalau penjual belum merespons, hubungi admin Merchku.'
        )
        links = [{'label': 'Buka Pesan', 'url': url_for('chat.inbox')}] if is_customer else []
    elif intent == 'payment':
        reply = (
            'Metode pembayaran di Merchku:\n'
            '• Transfer bank, QRIS, atau e-wallet — bayar lalu unggah bukti di halaman pesanan\n'
            '• COD — bayar tunai saat barang diterima\n'
            '• Pembayaran online otomatis (QRIS/transfer/e-wallet) bila sedang aktif\n'
            'Setelah bukti diunggah, status jadi "Menunggu verifikasi" sampai dicek admin.'
        )
        suggestions = ['Cek status pesanan', 'Ongkir', 'Cara belanja']
    elif intent == 'shipping':
        reply = (
            f'Pengiriman tersedia lewat {COURIERS}. Ongkir dihitung saat checkout sesuai alamat '
            'di profilmu; kalau tarif otomatis belum aktif, ongkir dikonfirmasi admin setelah '
            'pesanan dibuat. Lama kirim mengikuti layanan kurir yang kamu pilih.'
        )
        links = [{'label': 'Atur alamat', 'url': url_for('profil.index')}] if logged_in else []
    elif intent == 'size':
        reply = SIZE_CHART
        products = search_products(text)
        suggestions = ['Hoodie', 'Kaos', 'Jaket']
    elif intent == 'discount':
        ratio = db.cast(Product.price, db.Float) / Product.original_price
        products = (
            Product.query.filter(Product.is_active.is_(True), Product.original_price > Product.price)
            .order_by(ratio.asc()).limit(4).all()
        )
        reply = (
            'Ini produk yang lagi diskon. Harga coret dan persen diskonnya tertera di setiap produk.'
            if products else 'Saat ini belum ada produk yang sedang diskon. Cek lagi nanti ya!'
        )
        links = [{'label': 'Semua produk diskon', 'url': url_for('katalog.index', sort='diskon')}]
    elif intent == 'bestseller':
        ids = best_seller_ids(4)
        found = {p.id: p for p in Product.query.filter(Product.id.in_(ids)).all()} if ids else {}
        products = [found[i] for i in ids if i in found]
        reply = 'Ini produk paling laris di Merchku.' if products else 'Belum ada data produk terlaris.'
        links = [{'label': 'Lihat semua terlaris', 'url': url_for('katalog.index', sort='terlaris')}]
    elif intent == 'account':
        reply = (
            'Soal akun:\n'
            '• Daftar: pilih Pembeli untuk belanja, atau Penjual untuk membuka toko.\n'
            '• Ganti password: Akun → Keamanan Akun (saat sudah login).\n'
            '• Lupa password: belum ada reset otomatis, silakan hubungi admin Merchku.'
        )
        links = (
            [{'label': 'Keamanan Akun', 'url': url_for('profil.keamanan')}] if logged_in
            else [{'label': 'Masuk', 'url': url_for('auth.login')}, {'label': 'Daftar', 'url': url_for('auth.register')}]
        )
    elif intent == 'seller':
        reply = (
            'Mau jualan di Merchku? Daftar akun baru dan pilih peran "Penjual". Setelah itu kamu '
            'bisa atur profil toko, menambah produk, dan memproses pesanan dari Dashboard Penjual. '
            'Catatan: akun pembeli yang sudah ada tidak bisa diubah jadi akun penjual.'
        )
        links = [{'label': 'Daftar penjual', 'url': url_for('auth.register')}]
    elif intent == 'review':
        reply = 'Ulasan bisa kamu tulis di halaman produk setelah pesanannya berstatus Selesai.'
    elif intent == 'human':
        reply = (
            'Untuk ngobrol langsung dengan penjual, buka halaman produk lalu tekan "Chat Penjual". '
            'Semua percakapan tersimpan di menu Pesan.'
        )
        links = [{'label': 'Buka Pesan', 'url': url_for('chat.inbox')}] if logged_in and user.role in ('customer', 'seller') else []
    elif intent == 'how_to_buy':
        reply = (
            'Cara belanja di Merchku:\n'
            '1. Masuk sebagai pembeli\n'
            '2. Pilih produk → pilih ukuran & jumlah → Tambah ke Keranjang / Beli Sekarang\n'
            '3. Checkout: cek alamat, pilih kurir & pembayaran → Buat Pesanan\n'
            '4. Bayar & unggah bukti (jika manual), lalu pantau di Pesanan Saya'
        )
        links = [{'label': 'Mulai belanja', 'url': url_for('katalog.index')}]
    else:
        products = search_products(text)
        if products:
            reply = 'Aku nemu produk ini buat kamu. Tap untuk lihat detail, ukuran, dan stoknya.'
            links = [{'label': 'Cari lebih banyak', 'url': url_for('katalog.index', q=message[:60])}]
        else:
            reply = (
                'Hmm, aku belum paham pertanyaanmu. Coba tanya soal produk (mis. "hoodie hitam"), '
                'status pesanan, ongkir, pembayaran, atau ukuran.'
            )

    return {
        'reply': reply,
        'products': [product_payload(p) for p in products],
        'links': links,
        'suggestions': suggestions,
        'intent': intent or ('search' if products else 'unknown'),
    }
