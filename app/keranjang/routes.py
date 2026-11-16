from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db, limiter
from app.core.utils import get_client_ip, log_access_denied
from app.katalog.models import SIZES, Product, ProductSizeStock
from app.keranjang.models import MAX_QTY_PER_ITEM, CartItem
from app.security_logger import sec_log

bp = Blueprint('keranjang', __name__, url_prefix='/keranjang')


def _log(event, **kw):
    """Helper log dengan konteks request/user.

    Nilai default hanya dipakai bila pemanggil tidak menyediakannya sendiri,
    sehingga pemanggil boleh meng-override (mis. `user_id`) tanpa error.
    """
    level = kw.pop('level', None)  # None: sec_log memilih info/warning sesuai event
    kw.setdefault('ip', get_client_ip(current_app.config.get('TRUSTED_PROXIES')))
    kw.setdefault('path', request.path)
    kw.setdefault('method', request.method)
    kw.setdefault('user_id', getattr(current_user, 'id', None))
    kw.setdefault('email', getattr(current_user, 'email', None))
    kw.setdefault('role', getattr(current_user, 'role', None))
    sec_log(event=event, level=level, **kw)


def _validate_qty(raw) -> int:
    """Parse dan validasi quantity: integer, 1-Max_QTY_PER_ITEM."""
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        abort(400)
    if qty < 1 or qty > MAX_QTY_PER_ITEM:
        abort(400)
    return qty


def _validate_size(product: Product, size_raw) -> str | None:
    """Validasi ukuran terhadap produk. Kembalikan None bila produk tidak pakai ukuran."""
    if not product.use_sizes:
        return None
    size = (size_raw or '').strip().upper()
    if size not in SIZES:
        abort(400)
    return size


def _available_stock(product: Product, size: str | None) -> int:
    """Stok tersedia sesuai mode produk."""
    if product.use_sizes:
        ss = ProductSizeStock.query.filter_by(
            product_id=product.id, size=size
        ).first()
        return ss.stock if ss else 0
    return product.stock or 0


# ---------- routes ----------

@bp.route('/')
@login_required
def index():
    items = (
        CartItem.query
        .filter_by(user_id=current_user.id)
        .order_by(CartItem.added_at.desc())
        .all()
    )
    # Hitung total di server
    total = sum(
        item.product.price * item.quantity
        for item in items
        if item.product and item.product.is_active
    )
    return render_template('keranjang/index.html', items=items, total=total)


@bp.route('/tambah', methods=['POST'])
@login_required
@limiter.limit(
    '30 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
)
def tambah():
    """Tambah item ke keranjang. Harga TIDAK diambil dari form."""
    product_id = request.form.get('product_id', type=int)
    size_raw = request.form.get('size', '')
    qty = _validate_qty(request.form.get('quantity', 1))

    if not product_id:
        abort(400)

    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        abort(404)

    size = _validate_size(product, size_raw)

    # Cek stok tersedia
    stok = _available_stock(product, size)
    if stok <= 0:
        flash('Stok produk habis.', 'warning')
        return redirect(url_for('katalog.detail', pid=product_id))

    # Upsert: kalau sudah ada, tambah qty; kalau belum, buat baru
    item = CartItem.query.filter_by(
        user_id=current_user.id,
        product_id=product_id,
        size=size,
    ).first()

    if item:
        new_qty = item.quantity + qty
        if new_qty > MAX_QTY_PER_ITEM:
            new_qty = MAX_QTY_PER_ITEM
        if new_qty > stok:
            flash(f'Stok tidak mencukupi (tersisa {stok}).', 'warning')
            return redirect(url_for('katalog.detail', pid=product_id))
        item.quantity = new_qty
    else:
        if qty > stok:
            flash(f'Stok tidak mencukupi (tersisa {stok}).', 'warning')
            return redirect(url_for('katalog.detail', pid=product_id))
        item = CartItem(
            user_id=current_user.id,
            product_id=product_id,
            size=size,
            quantity=qty,
        )
        db.session.add(item)

    db.session.commit()
    _log('cart_item_added', product_id=product_id, size=size, quantity=qty)
    flash('Produk ditambahkan ke keranjang.', 'success')

    if request.form.get('buy_now'):
        return redirect(url_for('pesanan.checkout'))
    return redirect(url_for('keranjang.index'))


@bp.route('/ubah/<int:item_id>', methods=['POST'])
@login_required
@limiter.limit('30 per hour', key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr)
def ubah(item_id):
    """Ubah quantity item keranjang. Hanya boleh milik user sendiri (anti-IDOR)."""
    item = db.session.get(CartItem, item_id)
    if not item:
        abort(404)
    if item.user_id != current_user.id:
        log_access_denied('cart_item', item_id, reason='ownership')
        abort(403)

    qty = _validate_qty(request.form.get('quantity', 1))

    if not item.product or not item.product.is_active:
        flash('Produk tidak tersedia.', 'warning')
        return redirect(url_for('keranjang.index'))

    stok = _available_stock(item.product, item.size)
    if qty > stok:
        flash(f'Stok tidak mencukupi (tersisa {stok}).', 'warning')
        return redirect(url_for('keranjang.index'))

    item.quantity = qty
    db.session.commit()
    _log('cart_item_updated', product_id=item.product_id, size=item.size, quantity=qty, item_id=item_id)
    flash('Keranjang diperbarui.', 'success')
    return redirect(url_for('keranjang.index'))


@bp.route('/hapus/<int:item_id>', methods=['POST'])
@login_required
@limiter.limit('30 per hour', key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr)
def hapus(item_id):
    """Hapus item dari keranjang. Hanya boleh milik user sendiri (anti-IDOR)."""
    item = db.session.get(CartItem, item_id)
    if not item:
        abort(404)
    if item.user_id != current_user.id:
        log_access_denied('cart_item', item_id, reason='ownership')
        abort(403)

    prod_id = item.product_id
    size = item.size
    db.session.delete(item)
    db.session.commit()
    _log('cart_item_removed', product_id=prod_id, size=size, item_id=item_id)
    flash('Item dihapus dari keranjang.', 'success')
    return redirect(url_for('keranjang.index'))
