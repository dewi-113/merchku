from datetime import UTC, datetime, timedelta

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user
from sqlalchemy import or_

from app import db, limiter
from app.auth.decorators import role_required
from app.chat.models import ChatMessage, ChatThread
from app.katalog.models import Product

bp = Blueprint('chat', __name__, url_prefix='/chat')
MAX_MESSAGE_LENGTH = 3000


@bp.before_request
@role_required('customer', 'seller')
def _chat_roles_only():
    pass


def _thread_or_403(thread_id):
    thread = db.session.get(ChatThread, thread_id)
    if thread is None:
        abort(404)
    if current_user.id not in (thread.customer_id, thread.seller_id):
        abort(403)
    return thread


def _my_threads():
    return (
        ChatThread.query
        .filter(or_(ChatThread.customer_id == current_user.id, ChatThread.seller_id == current_user.id))
        .order_by(ChatThread.updated_at.desc())
        .all()
    )


def to_local(value):
    """Waktu di database disimpan UTC; tampilkan dalam zona waktu toko (default WIB)."""
    return value + timedelta(hours=current_app.config.get('TIMEZONE_OFFSET_HOURS', 7))


def day_label(value):
    local = to_local(value).date()
    today = to_local(datetime.now(UTC).replace(tzinfo=None)).date()
    if local == today:
        return 'Hari ini'
    if local == today - timedelta(days=1):
        return 'Kemarin'
    return local.strftime('%d %b %Y')


def _message_payload(message):
    return {
        'id': message.id,
        'body': message.body,
        'mine': message.sender_id == current_user.id,
        'time': to_local(message.created_at).strftime('%H:%M'),
        'day': day_label(message.created_at),
    }


def _wants_json():
    return request.headers.get('X-Requested-With') == 'fetch'


@bp.app_template_filter('chat_time')
def _chat_time_filter(value):
    """Label waktu daftar percakapan: jam (hari ini), Kemarin, atau tanggal."""
    label = day_label(value)
    return to_local(value).strftime('%H:%M') if label == 'Hari ini' else label


@bp.app_template_global('chat_day_label')
def _chat_day_label(value):
    return day_label(value)


@bp.app_template_global('chat_local_time')
def _chat_local_time(value):
    return to_local(value).strftime('%H:%M')


@bp.route('/')
def inbox():
    return render_template('chat/inbox.html', threads=_my_threads())


@bp.route('/mulai/<int:product_id>', methods=['POST'])
@role_required('customer')
def start(product_id):
    product = db.session.get(Product, product_id)
    if not product or not product.is_active:
        abort(404)
    seller = product.owner
    if not seller or seller.role != 'seller':
        flash('Produk ini belum memiliki penjual yang bisa dihubungi.', 'warning')
        return redirect(url_for('katalog.detail', pid=product.id))
    if seller.id == current_user.id:
        abort(403)

    thread = ChatThread.query.filter_by(
        customer_id=current_user.id,
        seller_id=seller.id,
    ).first()
    if thread is None:
        thread = ChatThread(customer_id=current_user.id, seller_id=seller.id)
        db.session.add(thread)
        db.session.commit()

    return redirect(url_for('chat.thread_detail', thread_id=thread.id, produk=product.id))


@bp.route('/<int:thread_id>', methods=['GET', 'POST'])
@limiter.limit('30 per hour', methods=['POST'])
def thread_detail(thread_id):
    thread = _thread_or_403(thread_id)
    if request.method == 'POST':
        body = (request.form.get('body') or '').strip()
        error = None
        if not body:
            error = 'Tulis pesan sebelum mengirim.'
        elif len(body) > MAX_MESSAGE_LENGTH:
            error = f'Pesan maksimal {MAX_MESSAGE_LENGTH} karakter.'
        if error:
            if _wants_json():
                return jsonify({'ok': False, 'error': error}), 400
            flash(error, 'warning')
        else:
            message = ChatMessage(thread_id=thread.id, sender_id=current_user.id, body=body)
            db.session.add(message)
            thread.updated_at = datetime.now(UTC).replace(tzinfo=None)
            db.session.commit()
            if _wants_json():
                return jsonify({'ok': True, 'message': _message_payload(message)})
            return redirect(url_for('chat.thread_detail', thread_id=thread.id))

    # Produk yang sedang ditanyakan (dari tombol Chat Penjual di halaman produk)
    asked_product = None
    produk_id = request.args.get('produk', type=int)
    if produk_id:
        candidate = db.session.get(Product, produk_id)
        if candidate and candidate.is_active and candidate.owner_id == thread.seller_id:
            asked_product = candidate

    return render_template(
        'chat/thread.html',
        thread=thread,
        threads=_my_threads(),
        asked_product=asked_product,
    )


@bp.get('/<int:thread_id>/pesan')
def thread_messages(thread_id):
    """Pesan baru setelah id tertentu (dipakai untuk pembaruan otomatis)."""
    thread = _thread_or_403(thread_id)
    after = request.args.get('after', 0, type=int)
    messages = (
        ChatMessage.query.filter(ChatMessage.thread_id == thread.id, ChatMessage.id > after)
        .order_by(ChatMessage.id).limit(100).all()
    )
    return jsonify({'messages': [_message_payload(m) for m in messages]})
