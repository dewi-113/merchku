from flask import render_template, request
from werkzeug.exceptions import HTTPException

from app.core.utils import get_client_ip
from app.security_logger import sec_log


def register_error_handlers(app):
    @app.errorhandler(400)
    def e400(e):
        sec_log(event='suspicious_request', ip=get_client_ip(app.config.get('TRUSTED_PROXIES')), path=request.path, method=request.method, reason='bad_request')
        return render_template('errors/400.html'), 400
    @app.errorhandler(403)
    def e403(e):
        sec_log(event='access_denied', ip=get_client_ip(app.config.get('TRUSTED_PROXIES')), path=request.path, method=request.method, resource=request.path)
        return render_template('errors/403.html'), 403
    @app.errorhandler(404)
    def e404(e):
        return render_template('errors/404.html'), 404
    @app.errorhandler(429)
    def e429(e):
        sec_log(event='rate_limited', ip=get_client_ip(app.config.get('TRUSTED_PROXIES')), path=request.path, method=request.method)
        return render_template('errors/429.html'), 429
    @app.errorhandler(500)
    def e500(e):
        sec_log(event='server_error', ip=get_client_ip(app.config.get('TRUSTED_PROXIES')), path=request.path, method=request.method)
        return render_template('errors/500.html'), 500
    @app.errorhandler(Exception)
    def e_any(e):
        if isinstance(e, HTTPException):
            code = e.code
            if code==400: return e400(e)
            if code==403: return e403(e)
            if code==404: return e404(e)
            if code==429: return e429(e)
            if code==500: return e500(e)
            return render_template('errors/500.html'), code
        # di mode testing/debug, biarkan exception naik agar mudah dilacak
        if app.config.get('PROPAGATE_EXCEPTIONS') or app.testing:
            raise e
        sec_log(event='server_error', ip=get_client_ip(app.config.get('TRUSTED_PROXIES')), path=request.path, method=request.method)
        return render_template('errors/500.html'), 500
