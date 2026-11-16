import contextlib
import os
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user
from sqlalchemy import func

from app import db, limiter
from app.admin.forms import OrderNoteForm, ProductForm, RoleChangeForm
from app.auth.decorators import role_required
from app.auth.models import User
from app.chat.models import ChatMessage, ChatThread
from app.core.uploads import UploadRejected, reencode_and_save, validate_image_upload
from app.core.utils import get_client_ip, log_access_denied
from app.katalog.follow_model import ShopFollow
from app.katalog.models import (
    SIZES,
    Product,
    ProductSizeStock,
    delete_or_archive_product,
)
from app.katalog.review_model import Review
from app.keranjang.models import CartItem
from app.pesanan.models import (
    ORDER_STATUSES,
    STOCK_RESERVED_STATUSES,
    Order,
    restore_reserved_stock,
)
from app.security_logger import sec_log

bp = Blueprint('admin', __name__, url_prefix='/admin')


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
@role_required('admin')
def _admin_only():
    pass


@bp.route('/')
def dashboard():
    stats = {
        'users': User.query.count(),
        'products': Product.query.count(),
        'orders': Order.query.count(),
        'pending_verification': Order.query.filter_by(status='menunggu_verifikasi').count(),
        'revenue': (
            db.session.query(func.coalesce(func.sum(Order.total_price), 0))
            .filter(
                db.or_(
                    db.and_(
                        Order.payment_method != 'cod',
                        Order.status.in_(['dibayar', 'dikirim', 'selesai']),
                    ),
                    db.and_(Order.payment_method == 'cod', Order.status == 'selesai'),
                )
            )
            .scalar()
        ),
    }
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    _log('admin_viewed_dashboard')
    return render_template('admin/dashboard.html', stats=stats, recent_orders=recent_orders)


# ---------- Produk ----------

@bp.route('/produk')
def produk_list():
    page = request.args.get('page', 1, type=int)
    q = Product.query.order_by(Product.created_at.desc())
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/produk_list.html', pagination=pagination)


def _save_product_image(file, kind='produk'):
    """Validasi & simpan gambar produk. Return nama file atau None bila tidak diupload.
    Raise UploadRejected bila tidak valid (caller yang log)."""
    if not file or not getattr(file, 'filename', ''):
        return None
    from app.core.uploads import MAX_PRODUCT_BYTES

    result = validate_image_upload(file, kind=kind, max_bytes=MAX_PRODUCT_BYTES)
    _, img = result
    return reencode_and_save(img, current_app.config['UPLOAD_PUBLIC'])


@bp.route('/produk/baru', methods=['GET', 'POST'])
@limiter.limit('20 per hour')
def produk_create():
    form = ProductForm()
    if form.validate_on_submit():
        try:
            image_name = _save_product_image(form.image.data, kind='produk')
        except UploadRejected as e:
            _log(
                'file_upload_rejected',
                jenis='produk',
                nama_asli=getattr(form.image.data, 'filename', ''),
                alasan=e.reason,
                user_id=current_user.id,
            )
            flash(f'Gambar ditolak: {e.reason}', 'danger')
            return render_template('admin/produk_form.html', form=form), 400
        if image_name:
            _log('file_upload_success', jenis='produk', nama_asli=form.image.data.filename, user_id=current_user.id)

        p = Product(
            name=form.name.data.strip(),
            description=(form.description.data or '').strip(),
            category=form.category.data,
            product_type=(form.product_type.data or '').strip() or None,
            color=(form.color.data or '').strip() or None,
            price=form.price.data,
            original_price=form.original_price.data or None,
            weight_gram=form.weight_gram.data or 500,
            is_active=bool(form.is_active.data),
            is_fragile=bool(form.is_fragile.data),
            use_sizes=bool(form.use_sizes.data),
            stock=0 if form.use_sizes.data else (form.stock.data or 0),
            image=image_name,
        )
        db.session.add(p)
        db.session.flush()
        if p.use_sizes:
            for size in SIZES:
                val = getattr(form, f'stock_{size}').data
                db.session.add(ProductSizeStock(product_id=p.id, size=size, stock=int(val or 0)))
        db.session.commit()
        _log('produk_created', produk_id=p.id, product_name=p.name, user_id=current_user.id)
        flash('Produk dibuat.', 'success')
        return redirect(url_for('admin.produk_list'))
    return render_template('admin/produk_form.html', form=form)


@bp.route('/produk/<int:pid>/edit', methods=['GET', 'POST'])
def produk_edit(pid):
    p = db.session.get(Product, pid) or abort(404)
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
            _log(
                'file_upload_rejected',
                jenis='produk',
                nama_asli=getattr(form.image.data, 'filename', ''),
                alasan=e.reason,
                user_id=current_user.id,
            )
            flash(f'Gambar ditolak: {e.reason}', 'danger')
            return render_template('admin/produk_form.html', form=form, product=p), 400

        p.name = form.name.data.strip()
        p.description = (form.description.data or '').strip()
        p.category = form.category.data
        p.product_type = (form.product_type.data or '').strip() or None
        p.color = (form.color.data or '').strip() or None
        p.price = form.price.data
        p.original_price = form.original_price.data or None
        p.weight_gram = form.weight_gram.data or 500
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
            # hapus stok ukuran lama
            for ss in list(p.stock_sizes):
                db.session.delete(ss)
        if image_name:
            # hapus gambar lama
            if p.image:
                with contextlib.suppress(OSError):
                    os.remove(os.path.join(current_app.config['UPLOAD_PUBLIC'], p.image))
            p.image = image_name
            _log('file_upload_success', jenis='produk', nama_asli=form.image.data.filename, user_id=current_user.id)
        db.session.commit()
        _log('produk_updated', produk_id=p.id, product_name=p.name, user_id=current_user.id)
        flash('Produk diperbarui.', 'success')
        return redirect(url_for('admin.produk_list'))
    return render_template('admin/produk_form.html', form=form, product=p)


@bp.route('/produk/<int:pid>/hapus', methods=['POST'])
def produk_delete(pid):
    p = db.session.get(Product, pid) or abort(404)
    result = delete_or_archive_product(p, current_app.config['UPLOAD_PUBLIC'])
    if result == 'archived':
        _log('produk_archived', produk_id=pid, user_id=current_user.id)
        flash('Produk sudah ada di riwayat pesanan, jadi dinonaktifkan (tidak tampil di katalog).', 'warning')
    else:
        _log('produk_deleted', produk_id=pid, user_id=current_user.id)
        flash('Produk dihapus.', 'success')
    return redirect(url_for('admin.produk_list'))


# ---------- Pengguna ----------

@bp.route('/pengguna')
def user_list():
    page = request.args.get('page', 1, type=int)
    q = User.query.order_by(User.created_at.desc())
    pagination = q.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/user_list.html', pagination=pagination)


@bp.route('/pengguna/<int:uid>/status', methods=['POST'])
def user_status(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.id == current_user.id:
        flash('Tidak bisa menonaktifkan akun sendiri.', 'danger')
        return redirect(url_for('admin.user_list'))
    u.is_active = not u.is_active
    db.session.commit()
    _log('user_status_changed', target_user_id=u.id, target_email=u.email,
         new_status='aktif' if u.is_active else 'nonaktif', user_id=current_user.id)
    flash(f'Status {u.email} -> {"aktif" if u.is_active else "nonaktif"}.', 'success')
    return redirect(url_for('admin.user_list'))


@bp.route('/pengguna/<int:uid>/role', methods=['GET', 'POST'])
def user_role(uid):
    u = db.session.get(User, uid) or abort(404)
    form = RoleChangeForm()
    if request.method == 'GET':
        form.role.data = u.role
    if form.validate_on_submit():
        if form.confirm.data.strip().lower() != u.email.lower():
            log_access_denied('user_role_confirmation', u.id, reason='confirm_mismatch')
            flash('Konfirmasi tidak cocok.', 'danger')
            return render_template('admin/user_role.html', user=u, form=form), 403
        new_role = form.role.data
        if u.id == current_user.id and new_role != 'admin':
            flash('Tidak bisa menurunkan role akun sendiri.', 'danger')
            return render_template('admin/user_role.html', user=u, form=form), 403
        old = u.role
        u.role = new_role
        db.session.commit()
        _log('user_role_changed', target_user_id=u.id, target_email=u.email,
             old_role=old, new_role=u.role, user_id=current_user.id)
        flash(f'Role {u.email}: {old} -> {u.role}.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_role.html', user=u, form=form)


def _user_has_history(uid):
    """True bila pengguna terkait data yang wajib dijaga (FK tanpa cascade)."""
    checks = (
        db.session.query(Order.id).filter(Order.user_id == uid),
        db.session.query(Product.id).filter(Product.owner_id == uid),
        db.session.query(Review.id).filter(Review.user_id == uid),
        db.session.query(ChatThread.id).filter(
            db.or_(ChatThread.customer_id == uid, ChatThread.seller_id == uid)
        ),
        db.session.query(ChatMessage.id).filter(ChatMessage.sender_id == uid),
    )
    return any(q.first() for q in checks)


@bp.route('/pengguna/<int:uid>/hapus', methods=['POST'])
def user_delete(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.id == current_user.id:
        flash('Tidak bisa menghapus akun sendiri.', 'danger')
        return redirect(url_for('admin.user_list'))
    if _user_has_history(u.id):
        flash('Pengguna ini punya riwayat (pesanan, produk, ulasan, atau chat) sehingga '
              'tidak bisa dihapus. Nonaktifkan saja akunnya.', 'warning')
        return redirect(url_for('admin.user_list'))
    email = u.email
    CartItem.query.filter_by(user_id=u.id).delete()
    ShopFollow.query.filter(
        db.or_(ShopFollow.seller_id == u.id, ShopFollow.follower_id == u.id)
    ).delete(synchronize_session=False)
    db.session.delete(u)
    db.session.commit()
    _log('user_deleted', target_user_id=uid, target_email=email, user_id=current_user.id)
    flash('Pengguna dihapus.', 'success')
    return redirect(url_for('admin.user_list'))


# ═══════════════════════════════════════════════════════════════════
# Pesanan — approval, list, detail, lihat bukti bayar, ubah status
# ═══════════════════════════════════════════════════════════════════

@bp.route('/pesanan')
def pesanan_list():
    """Daftar semua pesanan, bisa filter per status."""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status', '').strip()
    q = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        q = q.filter(Order.status == status_filter)

    pagination = q.paginate(page=page, per_page=20, error_out=False)
    return render_template('admin/pesanan_list.html', pagination=pagination,
                           ORDER_STATUSES=ORDER_STATUSES, status_filter=status_filter)




@bp.route('/pesanan/<int:order_id>')
def pesanan_detail(order_id):
    """Detail pesanan lengkap untuk admin."""
    order = db.session.get(Order, order_id) or abort(404)
    form = OrderNoteForm()
    return render_template('admin/pesanan_detail.html', order=order, form=form,
                           ORDER_STATUSES=ORDER_STATUSES)




@bp.route('/pesanan/<int:order_id>/bukti')
def pesanan_bukti(order_id):
    """Admin lihat bukti bayar. Sajikan dari direktori privat."""
    order = db.session.get(Order, order_id) or abort(404)
    if not order.payment_proof:
        abort(404)
    private_dir = current_app.config['UPLOAD_PRIVATE']
    fname = order.payment_proof
    fpath = os.path.join(private_dir, fname)
    if not os.path.isfile(fpath):
        abort(404)
    ext = os.path.splitext(fname)[1].lower()
    mime = 'application/pdf' if ext == '.pdf' else 'image/jpeg'
    _log('bukti_bayar_download', order_id=order_id, fname=fname)
    response = send_from_directory(
        private_dir, fname, mimetype=mime,
        as_attachment=True,
        download_name=f'bukti_bayar_{order_id}{ext}',
    )
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.route('/pesanan/<int:order_id>/status', methods=['POST'])
def pesanan_ubah_status(order_id):
    """
    Admin mengubah status pesanan (termasuk approve/reject bukti bayar).
    Validasi: transisi harus ada di VALID_TRANSITIONS.
    Catat ke log: bukti_bayar_approved / bukti_bayar_rejected / order_status_changed.
    """
    order = db.session.get(Order, order_id) or abort(404)
    old_status = order.status
    new_status = request.form.get('new_status', '').strip()
    admin_note = request.form.get('admin_note', '').strip()

    if not order.can_transition_to(new_status):
        flash(f'Transisi {order.status} → {new_status} tidak valid.', 'danger')
        return redirect(url_for('admin.pesanan_detail', order_id=order_id))

    # Pesanan yang dibatalkan sebelum dibayar harus mengembalikan stok
    # yang masih di-reserve, supaya stok tidak hilang dari inventaris.
    if new_status == 'dibatalkan' and old_status in STOCK_RESERVED_STATUSES:
        try:
            restore_reserved_stock(order)
        except Exception:
            db.session.rollback()
            _log('server_error', reason='restore_stock_failed', order_id=order_id)
            flash('Gagal mengembalikan stok pesanan. Coba lagi.', 'danger')
            return redirect(url_for('admin.pesanan_detail', order_id=order_id))

    order.status = new_status
    if admin_note:
        order.admin_note = admin_note

    db.session.commit()

    # Log spesifik untuk approve/reject bukti bayar

    if old_status == 'menunggu_verifikasi' and new_status == 'dibayar':
        _log('bukti_bayar_approved', order_id=order_id, user_id=current_user.id)
    elif old_status == 'menunggu_verifikasi' and new_status == 'ditolak':
        _log('bukti_bayar_rejected', order_id=order_id, user_id=current_user.id, note=admin_note)

    _log('order_status_changed', order_id=order_id,
         old_status=old_status, new_status=new_status,
         actor='admin', admin_id=current_user.id)

    flash(f'Status pesanan #{order_id} diubah ke {new_status}.', 'success')
    return redirect(url_for('admin.pesanan_detail', order_id=order_id))


# ═══════════════════════════════════════════════════════════════════
# Laporan transaksi
# ═══════════════════════════════════════════════════════════════════

@bp.route('/laporan')
def laporan():
    """
    Ringkasan transaksi seluruh toko.
    Filter opsional: date_from, date_to (format YYYY-MM-DD).
    Tampilkan: total pesanan, omzet, breakdown per status.
    """
    date_from_str = request.args.get('date_from', '').strip()
    date_to_str = request.args.get('date_to', '').strip()


    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = datetime.strptime(date_from_str, '%Y-%m-%d')
        if date_to_str:
            date_to = datetime.strptime(date_to_str, '%Y-%m-%d')
            # inklusif: sampai akhir hari
            date_to = date_to.replace(hour=23, minute=59, second=59)
    except ValueError:
        flash('Format tanggal tidak valid. Gunakan YYYY-MM-DD.', 'danger')
        date_from_str = date_to_str = ''

    base_q = Order.query
    if date_from:
        base_q = base_q.filter(Order.created_at >= date_from)
    if date_to:
        base_q = base_q.filter(Order.created_at <= date_to)

    # Total semua pesanan di periode
    total_pesanan = base_q.count()

    # Filter periode yang sama, dipakai ulang untuk agregasi SUM
    periode_filters = []
    if date_from:
        periode_filters.append(Order.created_at >= date_from)
    if date_to:
        periode_filters.append(Order.created_at <= date_to)

    def _total_filter(*extra):
        return (
            db.session.execute(
                db.select(func.sum(Order.total_price))
                .where(*extra, *periode_filters)
            ).scalar()
            or 0
        )

    # Omzet: hanya pesanan dengan status dibayar/dikirim/selesai
    omzet = _total_filter(
        db.or_(
            db.and_(
                Order.payment_method != 'cod',
                Order.status.in_(['dibayar', 'dikirim', 'selesai']),
            ),
            db.and_(Order.payment_method == 'cod', Order.status == 'selesai'),
        )
    )

    # Breakdown per status
    status_counts = {}
    for s in ORDER_STATUSES:
        status_counts[s] = {
            'count': base_q.filter(Order.status == s).count(),
            'total': _total_filter(Order.status == s),
        }


    # Pesanan terbaru (10)
    recent_orders = base_q.order_by(Order.created_at.desc()).limit(10).all()

    _log('admin_viewed_laporan', date_from=date_from_str, date_to=date_to_str)

    return render_template(
        'admin/laporan.html',
        total_pesanan=total_pesanan,
        omzet=omzet,
        status_counts=status_counts,
        ORDER_STATUSES=ORDER_STATUSES,
        recent_orders=recent_orders,
        date_from=date_from_str,
        date_to=date_to_str,
    )
