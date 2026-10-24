from functools import wraps

from flask import abort, current_app, redirect, request, url_for
from flask_login import current_user

from app.core.utils import get_client_ip
from app.security_logger import sec_log


def role_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated:
                next_url = request.full_path if request.query_string else request.path
                return redirect(url_for('auth.login', next=next_url))
            if current_user.role not in roles:

                sec_log(
                    event='access_denied',
                    ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
                    path=request.path,
                    method=request.method,
                    user_id=current_user.id,
                    email=current_user.email,
                    role=current_user.role,
                    resource=request.path,
                    reason='role',
                )
                abort(403)
            return f(*a, **kw)
        return wrapper
    return deco
