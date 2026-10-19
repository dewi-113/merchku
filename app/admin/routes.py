import os

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

from app import db, limiter
from app.admin.forms import ProductForm, RoleChangeForm
from app.auth.decorators import role_required
from app.auth.models import User
from app.core.uploads import UploadRejected, reencode_and_save, validate_image_upload
from app.core.utils import get_client_ip, log_access_denied
from app.katalog.models import SIZES, Product, ProductSizeStock
from app.security_logger import sec_log

bp = Blueprint('admin', __name__, url_prefix='/admin')


def _log(event, **kw):
    sec_log(
        event=event,
        ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
        path=request.path,
        method=request.method,
        **kw,
    )


@bp.before_request
@role_required('admin')
def _admin_only():
    pass


@bp.route('/')
def dashboard():
    stats = {
        'users': User.query.count(),
        'products': Product.query.count(),
    }
    _log('admin_viewed_dashboard')
    return render_template('admin/dashboard.html', stats=stats)


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
            price=form.price.data,
            is_active=bool(form.is_active.data),
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
        p.price = form.price.data
        p.is_active = bool(form.is_active.data)
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
                try:
                    os.remove(os.path.join(current_app.config['UPLOAD_PUBLIC'], p.image))
                except OSError:
                    pass
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
    if p.image:
        try:
            os.remove(os.path.join(current_app.config['UPLOAD_PUBLIC'], p.image))
        except OSError:
            pass
    db.session.delete(p)
    db.session.commit()
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
    if form.validate_on_submit():
        if form.confirm.data.strip().lower() != u.email.lower():
            log_access_denied('user_role_confirmation', u.id, reason='confirm_mismatch')
            flash('Konfirmasi tidak cocok.', 'danger')
            return render_template('admin/user_role.html', user=u, form=form), 403
        old = u.role
        u.role = 'customer' if u.role == 'admin' else 'admin'
        db.session.commit()
        _log('user_role_changed', target_user_id=u.id, target_email=u.email,
             old_role=old, new_role=u.role, user_id=current_user.id)
        flash(f'Role {u.email}: {old} -> {u.role}.', 'success')
        return redirect(url_for('admin.user_list'))
    return render_template('admin/user_role.html', user=u, form=form)


@bp.route('/pengguna/<int:uid>/hapus', methods=['POST'])
def user_delete(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.id == current_user.id:
        flash('Tidak bisa menghapus akun sendiri.', 'danger')
        return redirect(url_for('admin.user_list'))
    email = u.email
    db.session.delete(u)
    db.session.commit()
    _log('user_deleted', target_user_id=uid, target_email=email, user_id=current_user.id)
    flash('Pengguna dihapus.', 'success')
    return redirect(url_for('admin.user_list'))
