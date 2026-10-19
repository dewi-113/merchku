import os

from flask import Flask, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

from app.core.errors import register_error_handlers
from app.core.middleware import register_security_headers
from app.core.utils import get_client_ip
from app.security_logger import setup_security_logger
from config import config_map

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    from app.auth.models import User
    try:
        return db.session.get(User, int(user_id))
    except Exception:
        return None
def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    cfg = config_map.get(config_name or os.getenv('ENV') or os.getenv('FLASK_ENV') or 'dev','dev')
    app.config.from_object(cfg)
    if not app.config.get('SECRET_KEY'):
        # di dev saja: pakai secret acak sementara (tidak di-hardcode)
        import secrets

        app.config['SECRET_KEY'] = secrets.token_hex(32)
    os.makedirs(app.config['LOG_DIR'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_PUBLIC'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_PRIVATE'], exist_ok=True)
    os.makedirs('instance', exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    setup_security_logger(app)
    register_security_headers(app)
    register_error_handlers(app)

    from app.blueprints import register_blueprints
    register_blueprints(app)
    from app.core.routes import bp as core_bp
    app.register_blueprint(core_bp)

    from app.cli import create_admin
    app.cli.add_command(create_admin)

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
