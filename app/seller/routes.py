import contextlib
import os
import re
from datetime import UTC, datetime

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
from flask_login import current_user
from flask_wtf import FlaskForm
from sqlalchemy import func
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.validators import Length, Optional

from app import db, limiter
from app.admin.forms import ProductForm
from app.auth.decorators import role_required
from app.core.uploads import UploadRejected, reencode_and_save, validate_image_upload
from app.core.utils import get_client_ip
from app.core.validators import NoMarkup, SafeShopName
from app.katalog.models import (
    SIZES,
    Product,
    ProductSizeStock,
    delete_or_archive_product,
)
from app.katalog.review_model import Review
from app.pesanan.models import (
    STOCK_RESERVED_STATUSES,
    Order,
    OrderItem,
    restore_reserved_stock,
)
from app.security_logger import sec_log

bp = Blueprint('seller', __name__, url_prefix='/seller')

LOW_STOCK_LIMIT = 5  # peringatan stok menipis di dashboard


class ShopProfileForm(FlaskForm):
    shop_name = StringField('Nama Toko', validators=[Optional(), Length(min=3, max=120), SafeShopName()])
    shop_description = TextAreaField('Deskripsi Toko', validators=[Optional(), Length(max=2000), NoMarkup()])
    submit = SubmitField('Simpan')


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


@bp.before_request
@role_required('seller', 'admin')
def _seller_only():
    pass


@bp.context_processor
def _panel_badge():
    """Jumlah pesanan yang perlu tindakan penjual (badge di sidebar)."""
    if not current_user.is_authenticated:
        return {}
    q = (
        db.session.query(func.count(func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(db.or_(
            Order.status.in_(['menunggu_verifikasi', 'dibayar']),
            db.and_(Order.payment_method == 'cod', Order.status == 'menunggu_pembayaran'),
        ))
    )
    if current_user.role != 'admin':
        q = q.filter(Product.owner_id == current_user.id)
    return {'panel_badge': int(q.scalar() or 0)}


def _own_product_or_404(pid):
    """Ambil produk milik penjual ini. Admin boleh akses semua."""
    p = db.session.get(Product, pid)
    if p is None:
        abort(404)
    if current_user.role != 'admin' and p.owner_id != current_user.id:
        abort(403)
    return p


def _save_product_image(file, kind='produk'):
    if not file or not getattr(file, 'filename', ''):
        return None
    from app.core.uploads import MAX_PRODUCT_BYTES

    result = validate_image_upload(file, kind=kind, max_bytes=MAX_PRODUCT_BYTES)
    _, img = result
    return reencode_and_save(img, current_app.config['UPLOAD_PUBLIC'])


@bp.route('/')
def dashboard():
    base = Product.query
    if current_user.role != 'admin':
        base = base.filter(Product.owner_id == current_user.id)
    stats = {
        'products': base.count(),
        'active': base.filter(Product.is_active.is_(True)).count(),
    }
    # barang terjual (dari order item pada produk milik penjual)
    sold_q = (
        db.session.query(func.coalesce(func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Order.status.in_(['dibayar', 'dikirim', 'selesai']))
    )
    if current_user.role != 'admin':
        sold_q = sold_q.filter(Product.owner_id == current_user.id)
    stats['sold'] = int(sold_q.scalar() or 0)

    recent = base.order_by(Product.created_at.desc()).limit(8).all()
    low_stock = sorted(
        (p for p in base.filter(Product.is_active.is_(True)).all() if p.total_stock <= LOW_STOCK_LIMIT),
        key=lambda p: p.total_stock,
    )[:8]
    _log('seller_viewed_dashboard')
    return render_template(
        'seller/dashboard.html', stats=stats, recent=recent, perf=_shop_performance(),
        low_stock=low_stock, low_stock_limit=LOW_STOCK_LIMIT,
    )


def _shop_performance():
    """Ringkasan performa toko: pendapatan, pesanan, rating, pengikut, produk terlaris."""
    from app.katalog.follow_model import follower_counts
    from app.katalog.stats import SOLD_STATUSES

    is_admin = current_user.role == 'admin'

    def own(q):
        return q if is_admin else q.filter(Product.owner_id == current_user.id)

    items = own(
        db.session.query(OrderItem)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
    )

    def count_orders(*conds):
        return int(items.filter(*conds).with_entities(func.count(func.distinct(Order.id))).scalar() or 0)

    # Pendapatan = uang yang sudah diterima: non-COD sejak dibayar, COD saat selesai
    # (sama dengan perhitungan omzet admin).
    paid = db.or_(
        db.and_(Order.payment_method != 'cod', Order.status.in_(SOLD_STATUSES)),
        db.and_(Order.payment_method == 'cod', Order.status == 'selesai'),
    )
    revenue = items.filter(paid).with_entities(
        func.coalesce(func.sum(OrderItem.quantity * OrderItem.unit_price), 0)
    ).scalar()
    orders_total = count_orders(Order.status != 'dibatalkan')
    orders_completed = count_orders(Order.status == 'selesai')

    rating_avg, rating_count = own(
        db.session.query(func.avg(Review.rating), func.count(Review.id))
        .join(Product, Product.id == Review.product_id)
    ).one()

    sold_qty = func.sum(OrderItem.quantity)
    top_products = (
        items.filter(Order.status.in_(SOLD_STATUSES))
        .with_entities(Product.id, Product.name, sold_qty.label('sold'),
                       func.sum(OrderItem.quantity * OrderItem.unit_price).label('revenue'))
        .group_by(Product.id, Product.name)
        .order_by(sold_qty.desc())
        .limit(5)
        .all()
    )

    return {
        'revenue': int(revenue or 0),
        'orders_total': orders_total,
        'orders_completed': orders_completed,
        'completion_rate': round(orders_completed * 100 / orders_total) if orders_total else 0,
        'to_verify': count_orders(db.or_(
            Order.status == 'menunggu_verifikasi',
            db.and_(Order.payment_method == 'cod', Order.status == 'menunggu_pembayaran'),
        )),
        'to_ship': count_orders(Order.status == 'dibayar'),
        'rating': round(float(rating_avg), 1) if rating_avg else None,
        'rating_count': int(rating_count or 0),
        'followers': 0 if is_admin else follower_counts([current_user.id])[current_user.id],
        'top_products': top_products,
    }


@bp.route('/toko', methods=['GET', 'POST'])
def shop_profile():
    """Penjual mengubah identitas tokonya (nama & deskripsi)."""
    form = ShopProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.shop_name = (form.shop_name.data or '').strip() or None
        current_user.shop_description = (form.shop_description.data or '').strip() or None
        db.session.commit()
        _log('seller_shop_updated')
        flash('Profil toko diperbarui.', 'success')
        return redirect(url_for('seller.shop_profile'))
    from app.profil.forms import AvatarForm

    return render_template('seller/shop_profile.html', form=form, av_form=AvatarForm(prefix='av'))


@bp.route('/produk')
def produk_list():
    page = request.args.get('page', 1, type=int)
    q = Product.query
    if current_user.role != 'admin':
        q = q.filter(Product.owner_id == current_user.id)
    pagination = q.order_by(Product.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template('seller/produk_list.html', pagination=pagination)


@bp.route('/produk/baru', methods=['GET', 'POST'])
@limiter.limit('20 per hour')
def produk_create():
    form = ProductForm()
    if form.validate_on_submit():
        try:
            image_name = _save_product_image(form.image.data, kind='produk')
        except UploadRejected as e:
            _log('file_upload_rejected', jenis='produk',
                 nama_asli=getattr(form.image.data, 'filename', ''), alasan=e.reason)
            flash(f'Gambar ditolak: {e.reason}', 'danger')
            return render_template('seller/produk_form.html', form=form), 400

        p = Product(
            name=form.name.data.strip(),
            description=(form.description.data or '').strip(),
            category=form.category.data,
            product_type=(form.product_type.data or '').strip() or None,
            color=(form.color.data or '').strip() or None,
            price=form.price.data,
            original_price=form.original_price.data or None,
            is_active=bool(form.is_active.data),
            is_fragile=bool(form.is_fragile.data),
            use_sizes=bool(form.use_sizes.data),
            stock=0 if form.use_sizes.data else (form.stock.data or 0),
            image=image_name,
            owner_id=current_user.id,
        )
        db.session.add(p)
        db.session.flush()
        if p.use_sizes:
            for size in SIZES:
                val = getattr(form, f'stock_{size}').data
                db.session.add(ProductSizeStock(product_id=p.id, size=size, stock=int(val or 0)))
        db.session.commit()
        _log('seller_produk_created', produk_id=p.id, product_name=p.name)
        flash('Produk berhasil ditambahkan.', 'success')
        return redirect(url_for('seller.produk_list'))
    return render_template('seller/produk_form.html', form=form)


@bp.route('/produk/<int:pid>/edit', methods=['GET', 'POST'])
def produk_edit(pid):
    p = _own_product_or_404(pid)
    form = ProductForm(obj=p)
    if request.method == 'GET':
        if p.use_sizes:
            for size in SIZES:
                ss = next((s for s in p.stock_sizes if s.size == size), None)
                getattr(form, f'stock_{size}').data = ss.stock if ss else 0
        else:
            form.stock.data = p.stock
    if form.validate_on_submit():
        try:
            image_name = _save_product_image(form.image.data, kind='produk')
        except UploadRejected as e:
            _log('file_upload_rejected', jenis='produk',
                 nama_asli=getattr(form.image.data, 'filename', ''), alasan=e.reason)
            flash(f'Gambar ditolak: {e.reason}', 'danger')
            return render_template('seller/produk_form.html', form=form, product=p), 400

        p.name = form.name.data.strip()
        p.description = (form.description.data or '').strip()
        p.category = form.category.data
        p.product_type = (form.product_type.data or '').strip() or None
        p.color = (form.color.data or '').strip() or None
        p.price = form.price.data
        p.original_price = form.original_price.data or None
        p.is_active = bool(form.is_active.data)
        p.is_fragile = bool(form.is_fragile.data)
        new_use_sizes = bool(form.use_sizes.data)
        p.use_sizes = new_use_sizes
        if new_use_sizes:
            p.stock = 0
            for size in SIZES:
                ss = next((s for s in p.stock_sizes if s.size == size), None)
                val = int(getattr(form, f'stock_{size}').data or 0)
                if ss:
                    ss.stock = val
                else:
                    db.session.add(ProductSizeStock(product_id=p.id, size=size, stock=val))
        else:
            p.stock = int(form.stock.data or 0)
            for ss in list(p.stock_sizes):
                db.session.delete(ss)
        if image_name:
            if p.image:
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(current_app.config['UPLOAD_PUBLIC'], p.image))
            p.image = image_name
        db.session.commit()
        _log('seller_produk_updated', produk_id=p.id, product_name=p.name)
        flash('Produk diperbarui.', 'success')
        return redirect(url_for('seller.produk_list'))
    return render_template('seller/produk_form.html', form=form, product=p)


@bp.route('/produk/<int:pid>/hapus', methods=['POST'])
def produk_delete(pid):
    p = _own_product_or_404(pid)
    result = delete_or_archive_product(p, current_app.config['UPLOAD_PUBLIC'])
    if result == 'archived':
        _log('seller_produk_archived', produk_id=pid)
        flash('Produk sudah ada di riwayat pesanan, jadi dinonaktifkan (tidak tampil di katalog).', 'warning')
    else:
        _log('seller_produk_deleted', produk_id=pid)
        flash('Produk dihapus.', 'success')
    return redirect(url_for('seller.produk_list'))


@bp.route('/produk/<int:pid>/ulasan')
def produk_ulasan(pid):
    """Penjual melihat semua ulasan untuk produk miliknya."""
    p = _own_product_or_404(pid)
    reviews = (
        Review.query.filter_by(product_id=p.id)
        .order_by(Review.created_at.desc())
        .all()
    )
    avg = (
        db.session.query(func.avg(Review.rating))
        .filter(Review.product_id == p.id)
        .scalar()
    ) or 0.0
    _log('seller_viewed_reviews', produk_id=p.id)
    return render_template(
        'seller/produk_ulasan.html', product=p, reviews=reviews, avg=f'{avg:.1f}'
    )


@bp.route('/produk/<int:pid>/ulasan/<int:rid>/balas', methods=['POST'])
def produk_ulasan_balas(pid, rid):
    """Penjual membalas ulasan pada produk miliknya."""
    p = _own_product_or_404(pid)
    review = db.session.get(Review, rid)
    if review is None or review.product_id != p.id:
        abort(404)
    reply = (request.form.get('seller_reply') or '').strip()
    if not reply:
        flash('Balasan tidak boleh kosong.', 'warning')
        return redirect(url_for('seller.produk_ulasan', pid=pid))
    if len(reply) > 2000:
        reply = reply[:2000]
    review.seller_reply = reply
    review.replied_at = datetime.now(UTC).replace(tzinfo=None)
    db.session.commit()
    _log('seller_review_replied', produk_id=pid, review_id=rid)
    flash('Balasan ulasan tersimpan.', 'success')
    return redirect(url_for('seller.produk_ulasan', pid=pid))


@bp.route('/pesanan')
def pesanan_list():
    """Pesanan yang berisi produk milik penjual ini."""
    page = request.args.get('page', 1, type=int)
    q = Order.query.join(OrderItem, OrderItem.order_id == Order.id).join(
        Product, Product.id == OrderItem.product_id
    )
    if current_user.role != 'admin':
        q = q.filter(Product.owner_id == current_user.id)
    q = q.distinct().order_by(Order.created_at.desc())
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    rows = []
    for o in pagination.items:
        mine = _seller_items(o)
        rows.append({
            'order': o,
            'items': mine,
            'quantity': sum(it.quantity for it in mine),
            'subtotal': sum(it.subtotal for it in mine),
            'multi_shop': len(mine) != len(o.items),
        })
    return render_template('seller/pesanan_list.html', pagination=pagination, rows=rows)


def _seller_order_or_404(order_id):
    """Ambil order yang memuat produk milik penjual ini. Admin boleh akses semua."""
    order = db.session.get(Order, order_id)
    if order is None:
        abort(404)
    if current_user.role == 'admin':
        return order
    owns = (
        db.session.query(OrderItem.id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(OrderItem.order_id == order_id, Product.owner_id == current_user.id)
        .first()
    )
    if not owns:
        abort(403)
    return order


def _seller_items(order):
    """Item pada order yang benar-benar milik penjual ini."""
    if current_user.role == 'admin':
        return order.items
    return [it for it in order.items if it.product and it.product.owner_id == current_user.id]


# Tindakan penjual per status (berlaku untuk semua metode pembayaran).
SELLER_ACTIONS = {
    'menunggu_pembayaran': ('dibayar', 'dibatalkan'),
    'menunggu_verifikasi': ('dibayar', 'ditolak'),
    'ditolak': ('dibayar', 'dibatalkan'),
    'dibayar': ('dikirim',),
    'dikirim': ('selesai',),
}


def _seller_owns_all(order):
    """True bila SEMUA item pesanan adalah produk milik penjual ini."""
    if current_user.role == 'admin':
        return True
    return bool(order.items) and all(
        it.product and it.product.owner_id == current_user.id for it in order.items
    )


def _seller_actions(order):
    return [st for st in SELLER_ACTIONS.get(order.status, ()) if order.can_transition_to(st)]


def _copy_private_file(fname):
    """Salin bukti bayar agar pesanan hasil pemisahan punya file sendiri."""
    import shutil
    import uuid

    private_dir = current_app.config['UPLOAD_PRIVATE']
    src = os.path.join(private_dir, os.path.basename(fname))
    if not os.path.isfile(src):
        return fname
    new_name = f'{uuid.uuid4().hex}{os.path.splitext(fname)[1]}'
    shutil.copyfile(src, os.path.join(private_dir, new_name))
    return new_name


def _split_off_seller_items(order):
    """Pisahkan produk milik penjual ini dari pesanan multi-toko menjadi pesanan baru.

    Dipakai saat penjual memproses pesanan lama yang berisi produk beberapa
    toko, supaya status hanya berubah untuk produk tokonya sendiri.
    Biaya tambahan (ongkir, layanan, dll.) tetap di pesanan asal.
    """
    mine = [it for it in order.items if it.product and it.product.owner_id == current_user.id]
    moved_total = sum(it.subtotal for it in mine)
    copy_fields = (
        'user_id', 'status', 'recipient_name', 'address', 'address_label', 'district',
        'city', 'postal_code', 'province', 'phone', 'delivery_note', 'courier',
        'shipping_service', 'shipping_duration', 'payment_method', 'admin_note',
    )
    new_order = Order(**{f: getattr(order, f) for f in copy_fields})
    new_order.shipping_cost = 0
    new_order.shipping_discount = 0
    new_order.service_fee = 0
    new_order.fragile_protection = False
    new_order.fragile_fee = 0
    new_order.total_price = moved_total
    if order.payment_proof:
        new_order.payment_proof = _copy_private_file(order.payment_proof)
    db.session.add(new_order)
    db.session.flush()
    for it in mine:
        it.order_id = new_order.id
    order.total_price = max(0, order.total_price - moved_total)
    db.session.flush()
    db.session.refresh(order)
    db.session.refresh(new_order)
    _log('order_split', order_id=order.id, new_order_id=new_order.id, moved_total=moved_total)
    return new_order


@bp.route('/pesanan/<int:order_id>')
def pesanan_detail(order_id):
    """Detail pesanan: hanya menampilkan item milik penjual ini."""
    order = _seller_order_or_404(order_id)
    items = _seller_items(order)
    subtotal = sum(it.subtotal for it in items)
    _log('seller_viewed_order', order_id=order_id)
    return render_template(
        'seller/pesanan_detail.html', order=order, items=items, subtotal=subtotal,
        actions=_seller_actions(order),
        multi_shop=not _seller_owns_all(order),
    )


@bp.route('/pesanan/<int:order_id>/status', methods=['POST'])
def pesanan_ubah_status(order_id):
    """Penjual memproses pesanan: konfirmasi/tolak pembayaran, terima/tolak COD,
    batalkan, kirim, dan selesaikan. Berlaku untuk semua metode pembayaran."""
    order = _seller_order_or_404(order_id)
    new_status = request.form.get('new_status', '').strip()

    if new_status not in _seller_actions(order):
        flash(f'Transisi {order.display_status} ke {new_status} tidak valid.', 'danger')
        return redirect(url_for('seller.pesanan_detail', order_id=order_id))

    resi = (request.form.get('tracking_number') or '').strip()
    if new_status == 'dikirim' and resi and not re.fullmatch(r'[A-Za-z0-9\-]{4,60}', resi):
        flash('Nomor resi hanya boleh huruf, angka, dan tanda minus (4-60 karakter).', 'danger')
        return redirect(url_for('seller.pesanan_detail', order_id=order_id))

    # Pesanan lama multi-toko: pisahkan produk toko ini lebih dulu.
    if not _seller_owns_all(order):
        order = _split_off_seller_items(order)
        flash(f'Produk toko Anda dipisah menjadi pesanan #{order.id}.', 'info')

    old_status = order.status
    is_cod = order.payment_method == 'cod'
    if new_status == 'dikirim' and resi:
        order.tracking_number = resi
    if new_status == 'dibatalkan' and old_status in STOCK_RESERVED_STATUSES:
        restore_reserved_stock(order)
    order.status = new_status
    db.session.commit()

    if is_cod and old_status == 'menunggu_pembayaran':
        _log('cod_confirmed' if new_status == 'dibayar' else 'cod_rejected',
             order_id=order.id, actor='seller')
    elif new_status == 'dibayar':
        _log('bukti_bayar_approved', order_id=order.id, actor='seller', manual=old_status != 'menunggu_verifikasi')
    elif new_status == 'ditolak':
        _log('bukti_bayar_rejected', order_id=order.id, actor='seller')
    _log('order_status_changed', order_id=order.id, old_status=old_status,
         new_status=new_status, actor='seller', seller_id=current_user.id)

    messages = {
        'dibayar': ('Pesanan COD #{id} diterima. Silakan kemas dan kirim.' if is_cod
                    else 'Pembayaran pesanan #{id} dikonfirmasi. Silakan kemas dan kirim.'),
        'ditolak': 'Bukti bayar pesanan #{id} ditolak. Pembeli diminta mengunggah ulang.',
        'dibatalkan': 'Pesanan #{id} dibatalkan dan stok dikembalikan.',
        'dikirim': 'Pesanan #{id} ditandai dikirim.' + (f' Resi: {resi}.' if resi else ''),
        'selesai': 'Pesanan #{id} ditandai selesai.',
    }
    flash(messages[new_status].format(id=order.id), 'success')
    return redirect(url_for('seller.pesanan_detail', order_id=order.id))
