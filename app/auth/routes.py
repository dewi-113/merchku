from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_user, logout_user

from app import db
from app.auth.forms import LoginForm, RegisterForm
from app.auth.models import User
from app.auth.security import hash_password, verify_password
from app.core.utils import get_client_ip
from app.security_logger import sec_log

bp = Blueprint('auth', __name__, url_prefix='/auth')

def get_ip():
    return get_client_ip(current_app.config.get('TRUSTED_PROXIES'))

@bp.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('core.healthz'))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()
        ip = get_ip()
        if not user:
            sec_log(event='login_failed', ip=ip, email=email, path='/auth/login', method='POST')
            flash('Email atau password salah.','danger')
            return render_template('auth/login.html', form=form)
        from datetime import datetime, timedelta
        if user.locked_until and user.locked_until > datetime.utcnow():
            sec_log(event='account_locked', ip=ip, user_id=user.id, email=user.email, role=user.role)
            flash('Akun terkunci. Coba lagi nanti.','danger')
            return render_template('auth/login.html', form=form)
        if not verify_password(user.password_hash, form.password.data):
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=15)
                sec_log(event='account_locked', ip=ip, user_id=user.id, email=user.email, role=user.role, reason='failed>=5')
            db.session.commit()
            sec_log(event='login_failed', ip=ip, user_id=user.id, email=user.email, role=user.role)
            flash('Email atau password salah.','danger')
            return render_template('auth/login.html', form=form)
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = datetime.utcnow()
        db.session.commit()
        login_user(user, remember=form.remember.data)
        sec_log(event='login_success', ip=ip, user_id=user.id, email=user.email, role=user.role)
        return redirect(url_for('core.healthz'))
    return render_template('auth/login.html', form=form)

@bp.route('/logout')
def logout():
    if current_user.is_authenticated:
        sec_log(event='logout', ip=get_ip(), user_id=current_user.id, email=current_user.email, role=current_user.role)
        logout_user()
    return redirect(url_for('auth.login'))

@bp.route('/register', methods=['GET','POST'])
def register():
    from app import limiter
    limiter.limit('5 per hour', key_func=get_remote_address)(lambda: None)
    if current_user.is_authenticated:
        return redirect(url_for('core.healthz'))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        if User.query.filter_by(email=email).first():
            flash('Email sudah terdaftar.','warning')
            return render_template('auth/register.html', form=form)
        u = User(email=email, password_hash=hash_password(form.password.data), role='customer', is_active=True)
        db.session.add(u)
        db.session.commit()
        sec_log(event='register_success', ip=get_ip(), user_id=u.id, email=u.email, role=u.role)
        flash('Registrasi berhasil. Silakan login.','success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)
