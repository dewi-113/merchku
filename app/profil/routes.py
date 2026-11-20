import contextlib
import os

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user

from app import db, limiter
from app.auth.security import hash_password, verify_password
from app.core.uploads import (
    MAX_AVATAR_BYTES,
    UploadRejected,
    reencode_and_save,
    validate_image_upload,
)
from app.core.utils import get_client_ip
from app.profil.forms import AvatarForm, GantiPasswordForm, ShippingAddressForm
from app.profil.models import (
    ADDRESS_FIELDS,
    MAX_ADDRESSES,
    Address,
    set_default,
    sync_user_default,
    user_addresses,
)
from app.security_logger import sec_log

bp = Blueprint('profil', __name__, url_prefix='/profil')


def _log(event, **kw):
    sec_log(
        event=event,
        ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
        path=request.path,
        method=request.method,
        **kw,
    )


# ---------- routes ----------

@bp.route('/')
@login_required
def index():
    """Halaman profil dan data penerima yang digunakan saat checkout."""
    return _render_profile(ShippingAddressForm(prefix='addr'))


def _render_profile(address_form, av_form=None, status=200, open_form=False):
    return render_template(
        'profil/index.html',
        av_form=av_form or AvatarForm(prefix='av'),
        address_form=address_form,
        addresses=user_addresses(current_user),
        max_addresses=MAX_ADDRESSES,
        open_form=open_form,
    ), status


def _own_address_or_404(aid):
    addr = db.session.get(Address, aid)
    if addr is None:
        abort(404)
    if addr.user_id != current_user.id:
        _log('access_denied', resource='address', resource_id=aid, user_id=current_user.id)
        abort(403)
    return addr


def _fill_address(addr, form):
    for field in ADDRESS_FIELDS:
        value = getattr(form, field).data
        setattr(addr, field, value.strip() if isinstance(value, str) and value.strip() else None)
    addr.address_label = form.address_label.data


@bp.route('/keamanan')
@login_required
def keamanan():
    """Halaman khusus untuk memperbarui kredensial akun."""
    return _render_security_form(GantiPasswordForm(prefix='pw'))


def _render_security_form(pw_form, status=200):
    response = make_response(
        render_template('profil/keamanan.html', pw_form=pw_form),
        status,
    )
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Pragma'] = 'no-cache'
    return response


@bp.route('/alamat', methods=['POST'])
@login_required
def simpan_alamat():
    """Tambah alamat baru ke buku alamat."""
    address_form = ShippingAddressForm(prefix='addr')
    existing = user_addresses(current_user)
    if len(existing) >= MAX_ADDRESSES:
        flash(f'Maksimal {MAX_ADDRESSES} alamat. Hapus alamat lama terlebih dahulu.', 'warning')
        return redirect(url_for('profil.index') + '#shipping-address')
    if not address_form.validate_on_submit():
        flash('Periksa kembali data penerima dan alamat pengiriman.', 'danger')
        return _render_profile(address_form, status=400, open_form=True)

    addr = Address(user_id=current_user.id)
    _fill_address(addr, address_form)
    db.session.add(addr)
    db.session.flush()
    if not existing or address_form.is_default.data:
        set_default(current_user, addr)
    db.session.commit()
    flash('Alamat berhasil ditambahkan.', 'success')
    return redirect(url_for('profil.index') + '#shipping-address')


@bp.route('/alamat/<int:aid>/ubah', methods=['GET', 'POST'])
@login_required
def ubah_alamat(aid):
    addr = _own_address_or_404(aid)
    form = ShippingAddressForm(prefix='addr', obj=addr)
    if request.method == 'GET':
        form.is_default.data = addr.is_default
    if form.validate_on_submit():
        _fill_address(addr, form)
        if form.is_default.data or addr.is_default:
            set_default(current_user, addr)
        db.session.commit()
        flash('Alamat berhasil diperbarui.', 'success')
        return redirect(url_for('profil.index') + '#shipping-address')
    if request.method == 'POST':
        flash('Periksa kembali data alamat.', 'danger')
    return render_template('profil/alamat_form.html', form=form, address=addr)


@bp.route('/alamat/<int:aid>/utama', methods=['POST'])
@login_required
def alamat_utama(aid):
    addr = _own_address_or_404(aid)
    set_default(current_user, addr)
    db.session.commit()
    flash(f'Alamat {addr.label_text} a.n. {addr.recipient_name} dijadikan alamat utama.', 'success')
    return redirect(url_for('profil.index') + '#shipping-address')


@bp.route('/alamat/<int:aid>/hapus', methods=['POST'])
@login_required
def hapus_alamat(aid):
    addr = _own_address_or_404(aid)
    was_default = addr.is_default
    db.session.delete(addr)
    db.session.flush()
    if was_default:
        nxt = (
            Address.query.filter_by(user_id=current_user.id)
            .order_by(Address.created_at.asc(), Address.id.asc()).first()
        )
        if nxt:
            set_default(current_user, nxt)
        else:
            sync_user_default(current_user, None)
    db.session.commit()
    flash('Alamat dihapus.', 'success')
    return redirect(url_for('profil.index') + '#shipping-address')


@bp.route('/ganti-password', methods=['POST'])
@login_required
@limiter.limit(
    '10 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
)
def ganti_password():
    """Ganti password. Verifikasi password lama sebelum simpan yang baru."""
    pw_form = GantiPasswordForm(prefix='pw')

    if not pw_form.validate_on_submit():
        flash('Periksa kembali data password yang dimasukkan.', 'danger')
        return _render_security_form(pw_form, 400)

    if not verify_password(current_user.password_hash, pw_form.password_lama.data):
        _log('password_changed', success=False, reason='wrong_old_password')
        flash('Password lama salah.', 'danger')
        return _render_security_form(pw_form, 400)

    user = current_user._get_current_object()
    user.password_hash = hash_password(pw_form.password_baru.data)
    db.session.commit()
    # Sidik jari sesi berubah: login ulang di perangkat ini saja,
    # sesi di perangkat lain otomatis tidak berlaku lagi.
    login_user(user)
    _log('password_changed', success=True)
    flash('Password berhasil diubah. Sesi di perangkat lain sudah dikeluarkan.', 'success')
    return redirect(url_for('profil.index'))


@bp.route('/buka-toko', methods=['POST'])
@login_required
def buka_toko():
    """Endpoint lama dipertahankan, tetapi customer tidak dapat mengubah role."""
    if current_user.role in ('seller', 'admin'):
        return redirect(url_for('seller.dashboard'))
    flash('Akun pembeli tidak dapat diubah menjadi akun penjual.', 'warning')
    return redirect(url_for('profil.index'))


def _back_url():
    """Halaman asal setelah upload (hanya path lokal, cegah open redirect)."""
    nxt = request.form.get('next', '')
    if nxt.startswith('/') and not nxt.startswith('//') and '\\' not in nxt:
        return nxt
    return url_for('profil.index')


@bp.route('/upload-avatar', methods=['POST'])
@login_required
@limiter.limit(
    '10 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
)
def upload_avatar():
    """
    Upload avatar. Validasi: JPG/PNG, maks 1 MB, magic bytes + re-encode Pillow.
    Simpan di UPLOAD_PUBLIC dengan nama UUID.jpg.
    Hapus avatar lama setelah sukses.
    """
    av_form = AvatarForm(prefix='av')

    if av_form.validate_on_submit():
        file = av_form.avatar.data

        if not file or not getattr(file, 'filename', ''):
            flash('Pilih foto profil terlebih dahulu.', 'warning')
            return redirect(_back_url())

        try:
            result = validate_image_upload(file, kind='avatar', max_bytes=MAX_AVATAR_BYTES)
        except UploadRejected as e:
            _log(
                'file_upload_rejected',
                jenis='avatar',
                nama_asli=getattr(file, 'filename', ''),
                alasan=e.reason,
            )
            flash(f'Foto profil ditolak: {e.reason}', 'danger')
            if request.form.get('next'):
                return redirect(_back_url())
            return _render_profile(ShippingAddressForm(prefix='addr'), av_form=av_form, status=400)

        _, img = result
        pub_dir = current_app.config['UPLOAD_PUBLIC']

        # Hapus avatar lama
        if current_user.avatar:
            old_path = os.path.join(pub_dir, current_user.avatar)
            with contextlib.suppress(OSError):
                os.remove(old_path)

        fname = reencode_and_save(img, pub_dir)
        current_user.avatar = fname
        db.session.commit()

        _log('file_upload_success', jenis='avatar', nama_asli=getattr(file, 'filename', ''), fname=fname)
        flash('Foto profil berhasil diperbarui.', 'success')
    else:
        flash('Foto profil harus berformat JPG atau PNG.', 'danger')

    return redirect(_back_url())
