import os
import re

from flask import Blueprint, abort, current_app, jsonify, request, send_from_directory

from app import db
from app.core.utils import get_client_ip
from app.security_logger import sec_log

_UUID_FILE = re.compile(r'^[0-9a-f]{32}\.jpg$')

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


@bp.get('/media/produk/<path:filename>')
def produk_media(filename):
    """Sajikan gambar produk publik. Hanya nama file UUID.jpg yang valid."""
    if not _UUID_FILE.match(filename):
        sec_log(
            event='suspicious_request', level='warning',
            ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
            path=request.path, method=request.method, pattern='path_traversal',
        )
        abort(404)
    directory = current_app.config['UPLOAD_PUBLIC']
    if not os.path.exists(os.path.join(directory, filename)):
        abort(404)
    resp = send_from_directory(directory, filename)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
