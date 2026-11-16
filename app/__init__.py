import mimetypes
import os

from flask import Flask, current_app, request
from flask_limiter import Limiter
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from app.core.errors import register_error_handlers
from app.core.middleware import register_security_headers
from app.core.utils import get_client_ip
from app.security_logger import setup_security_logger
from config import DevConfig, config_map

mimetypes.add_type('application/manifest+json', '.webmanifest')

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()


def client_ip_key():
    """Kunci rate limit: IP asli pengunjung (tahan X-Forwarded-For palsu)."""
    return get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr


limiter = Limiter(key_func=client_ip_key)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Silakan masuk terlebih dahulu.'
login_manager.login_message_category = 'warning'
login_manager.session_protection = 'basic'


@login_manager.user_loader
def load_user(user_id):
    import hmac

    from app.auth.models import User

    try:
        uid, _, fingerprint = str(user_id).partition(':')
        user = db.session.get(User, int(uid))
    except Exception:
        return None
    if user is None or not user.is_active:
        return None
    # Sesi dari sebelum password diganti (atau format lama) tidak berlaku lagi
    if not hmac.compare_digest(fingerprint, user.session_fingerprint()):
        return None
    return user


def _cek_koneksi_mysql(app):
    """Di dev: beri peringatan jelas di terminal kalau MySQL belum menyala.

    Aplikasi tetap memakai MySQL (tidak pindah database); halaman yang dibuka
    selama MySQL mati menampilkan petunjuk 503 dari app/core/errors.py.
    """
    uri = str(app.config.get('SQLALCHEMY_DATABASE_URI', ''))
    if not uri.startswith('mysql') or app.config.get('TESTING') or not app.config.get('DEBUG'):
        return

    from sqlalchemy import create_engine, text

    engine = create_engine(
        app.config['SQLALCHEMY_DATABASE_URI'], connect_args={'connect_timeout': 3}
    )
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
    except Exception as exc:
        print(
            '\n[MERCHKU] PERINGATAN: MySQL tidak bisa dihubungi '
            f'({exc.__class__.__name__}).\n'
            '[MERCHKU] Nyalakan dulu di PowerShell (Administrator): Start-Service MySQL84\n',
            flush=True,
        )
    finally:
        engine.dispose()


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    cfg = config_map.get(
        config_name or os.getenv('ENV') or os.getenv('FLASK_ENV') or 'dev',
        DevConfig,
    )
    app.config.from_object(cfg)
    if not app.config.get('SECRET_KEY'):
        # di dev saja: pakai secret acak sementara (tidak di-hardcode)
        import secrets

        app.config['SECRET_KEY'] = secrets.token_hex(32)
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_PUBLIC'], exist_ok=True)
    os.makedirs(app.config['PRODUCT_PHOTOS_DIR'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_PRIVATE'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)
    _cek_koneksi_mysql(app)
    if app.config.get('PROXY_FIX_X_FOR'):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(
            app.wsgi_app, x_for=app.config['PROXY_FIX_X_FOR'], x_proto=1, x_host=1
        )

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    # Batas default rate limit diambil dari config (RATE_LIMIT_DEFAULT),
    # mis. "200 per minute". Dipasang sebelum init_app agar berlaku global.
    default_limit = app.config.get('RATE_LIMIT_DEFAULT')
    if default_limit:
        app.config['RATELIMIT_DEFAULT'] = default_limit
    limiter.init_app(app)

    @app.context_processor
    def _inject_cart_count():
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {'cart_count': 0}
        from app.keranjang.models import CartItem

        total = (
            db.session.query(db.func.coalesce(db.func.sum(CartItem.quantity), 0))
            .filter(CartItem.user_id == current_user.id)
            .scalar()
        )
        return {'cart_count': int(total or 0)}

    from app.katalog.follow_model import follower_counts
    from app.katalog.stats import product_stats, reviewer_name, sold_label
    app.add_template_global(product_stats)
    app.add_template_global(follower_counts)
    app.add_template_filter(sold_label, 'ringkas')
    app.add_template_filter(reviewer_name, 'nama_pengulas')

    setup_security_logger(app)
    register_security_headers(app)
    register_error_handlers(app)

    from app.blueprints import register_blueprints
    register_blueprints(app)
    from app.core.routes import bp as core_bp
    app.register_blueprint(core_bp)

    from app.cli import (
        create_admin,
        kunci_akun_demo,
        seed_demo,
        seed_promo,
        seed_sosial,
        seed_toko,
        sesuaikan_produk,
    )
    app.cli.add_command(create_admin)
    app.cli.add_command(seed_demo)
    app.cli.add_command(seed_toko)
    app.cli.add_command(seed_promo)
    app.cli.add_command(sesuaikan_produk)
    app.cli.add_command(seed_sosial)
    app.cli.add_command(kunci_akun_demo)

    @app.before_request
    def _https_forwarded():
        if app.config.get('SECURE_COOKIES') and request.headers.get('X-Forwarded-Proto')=='https':
            request.environ['wsgi.url_scheme'] = 'https'

    @app.before_request
    def _scan_suspicious():
        from app.core.utils import scan_request
        from app.security_logger import sec_log

        kind = scan_request(request.path)
        if kind:
            sec_log(
                event='suspicious_request',
                level='warning',
                ip=get_client_ip(app.config.get('TRUSTED_PROXIES')),
                path=request.path,
                method=request.method,
                pattern=kind,
            )

    return app
