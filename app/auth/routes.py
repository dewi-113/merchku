from datetime import UTC, datetime, timedelta

from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import CSRFError, validate_csrf
from wtforms import ValidationError

from app import client_ip_key, db, limiter
from app.auth.forms import LoginForm, RegisterForm
from app.auth.models import User
from app.auth.security import hash_password, verify_password
from app.core.utils import get_client_ip
from app.security_logger import sec_log

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Hash palsu untuk menyamakan waktu respon login saat email tidak terdaftar,
# supaya penyerang tidak bisa menebak email terdaftar dari lamanya respon.
_DUMMY_HASH = None


def _dummy_verify(password):
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password('dummy-password-untuk-timing')
    verify_password(_DUMMY_HASH, password or '')


def get_ip():
    return get_client_ip(current_app.config.get('TRUSTED_PROXIES'))


def _utcnow():
    """Waktu UTC naive, konsisten dengan kolom DateTime di model."""
    return datetime.now(UTC).replace(tzinfo=None)


def _safe_next(target):
    """
    Sanitasi parameter `next` agar tidak jadi open redirect.

    Hanya path relatif yang diizinkan (dimulai dengan '/' dan bukan '//').
    Nilai lain (mis. URL absolut ke domain lain) dibuang.
    """
    if not target:
        return None
    if not target.startswith('/') or target.startswith('//'):
        return None
    return target


@bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(
    lambda: current_app.config.get('RATELIMIT_LOGIN', '10 per minute; 50 per hour'),
    key_func=client_ip_key,
    methods=['POST'],
)
def login():
    if current_user.is_authenticated:
        return redirect(url_for('katalog.index'))
    form = LoginForm()
    next_url = _safe_next(request.args.get('next') or request.form.get('next'))
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        ip = get_ip()
        if not user:
            _dummy_verify(form.password.data)
            sec_log(event='login_failed', ip=ip, email=email, path='/auth/login', method='POST')
            flash('Email atau password salah.', 'danger')
            return render_template('auth/login.html', form=form, next_url=next_url)
        if not user.is_active:
            sec_log(event='login_failed', ip=ip, user_id=user.id, email=user.email, role=user.role, reason='inactive')
            flash('Akun ini dinonaktifkan. Hubungi admin.', 'danger')
            return render_template('auth/login.html', form=form, next_url=next_url)
        if user.locked_until and user.locked_until <= _utcnow():
            # masa kunci sudah habis: mulai hitung percobaan dari nol lagi
            user.locked_until = None
            user.failed_attempts = 0
        if user.locked_until and user.locked_until > _utcnow():
            sec_log(event='account_locked', ip=ip, user_id=user.id, email=user.email, role=user.role)
            flash('Akun terkunci. Coba lagi nanti.', 'danger')
            return render_template('auth/login.html', form=form, next_url=next_url)
        if not verify_password(user.password_hash, form.password.data):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.locked_until = _utcnow() + timedelta(minutes=15)
                sec_log(event='account_locked', ip=ip, user_id=user.id, email=user.email, role=user.role, reason='failed>=5')
            db.session.commit()
            sec_log(event='login_failed', ip=ip, user_id=user.id, email=user.email, role=user.role)
            flash('Email atau password salah.', 'danger')
            return render_template('auth/login.html', form=form, next_url=next_url)
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = _utcnow()
        db.session.commit()
        session.clear()  # buang isi sesi lama (cegah session fixation)
        login_user(user, remember=form.remember.data)
        sec_log(event='login_success', ip=ip, user_id=user.id, email=user.email, role=user.role)
        if next_url:
            return redirect(next_url)
        return redirect(url_for('katalog.index'))
    return render_template('auth/login.html', form=form, next_url=next_url)


@bp.route('/logout')
def logout():
    # Logout wajib membawa token CSRF agar situs lain tidak bisa memaksa logout
    try:
        validate_csrf(request.args.get('token', ''))
    except (ValidationError, CSRFError):
        if current_app.config.get('WTF_CSRF_ENABLED', True):
            return redirect(url_for('katalog.index'))
    if current_user.is_authenticated:
        sec_log(event='logout', ip=get_ip(), user_id=current_user.id, email=current_user.email, role=current_user.role)
        logout_user()
    session.clear()
    return redirect(url_for('auth.login'))


@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit(
    '5 per hour',
    key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr,
    methods=['POST'],
)
def register():
    if current_user.is_authenticated:
        return redirect(url_for('katalog.index'))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar.', 'warning')
            return render_template('auth/register.html', form=form)
        # role hanya boleh customer atau seller, tidak bisa admin lewat form
        role = form.role.data if form.role.data in ('customer', 'seller') else 'customer'
        u = User(email=email, password_hash=hash_password(form.password.data), role=role, is_active=True)
        db.session.add(u)
        db.session.commit()
        sec_log(event='register_success', ip=get_ip(), user_id=u.id, email=u.email, role=u.role)
        label = 'Penjual' if role == 'seller' else 'Pembeli'
        flash(f'Registrasi berhasil sebagai {label}. Silakan login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
