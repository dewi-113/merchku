from flask import Blueprint, abort, jsonify, request

from app import db
from app.core.utils import get_client_ip
from app.security_logger import sec_log

bp = Blueprint('core', __name__)

@bp.get('/healthz')
def healthz():
    ok = True
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        ok = False
    return jsonify({'status': 'ok' if ok else 'degraded', 'db': ok}), 200

@bp.get('/metrics')
def metrics():
    token = request.args.get('token') or request.headers.get('X-Metrics-Token')
    from flask import current_app
    if token != current_app.config.get('METRICS_TOKEN'):
        sec_log(event='access_denied', ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')), path='/metrics', method='GET', resource='metrics')
        abort(403)
    # placeholder minimal - prometheus exporternya bisa dipasang terpisah; cukup proteksi
    from flask import Response
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    data = generate_latest()
    return Response(data, mimetype=CONTENT_TYPE_LATEST)
