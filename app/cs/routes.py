from flask import Blueprint, current_app, jsonify, render_template, request
from flask_login import current_user

from app import csrf, limiter
from app.core.utils import get_client_ip
from app.cs.ai import ai_reply, is_enabled
from app.cs.engine import DEFAULT_SUGGESTIONS, answer

bp = Blueprint('cs', __name__, url_prefix='/bantuan')
MAX_QUESTION_LENGTH = 500


def _client_ip():
    return get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr


@bp.get('/')
def index():
    """Halaman chat Customer Service (terbuka untuk semua pengunjung)."""
    return render_template('cs/index.html', suggestions=DEFAULT_SUGGESTIONS, ai_enabled=is_enabled())


@bp.post('/tanya')
# Tanpa CSRF: endpoint ini hanya membaca data (tidak mengubah apa pun) dan
# jawabannya tidak bisa dibaca situs lain (tanpa CORS). Token CSRF di halaman
# yang dibiarkan terbuka lama bisa kedaluwarsa dan membuat CS gagal menjawab.
@csrf.exempt
@limiter.limit('20 per minute', key_func=_client_ip)
def tanya():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get('message') or '').strip()
    if not message:
        return jsonify({'error': 'Tulis pertanyaan dulu ya.'}), 400
    message = message[:MAX_QUESTION_LENGTH]
    history = payload.get('history') if isinstance(payload.get('history'), list) else []

    result = answer(message, current_user)
    result['source'] = 'otomatis'
    ai_text = ai_reply(message, history, current_user)
    if ai_text:
        result['reply'] = ai_text
        result['source'] = 'ai'
    return jsonify(result)
