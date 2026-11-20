from flask import Blueprint, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.notifikasi.models import Notification

bp = Blueprint('notifikasi', __name__, url_prefix='/notifikasi')


@bp.route('/')
@login_required
def index():
    items = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(100)
        .all()
    )
    unread_ids = [n.id for n in items if not n.is_read]
    html = render_template('notifikasi/index.html', items=items, unread_ids=set(unread_ids))
    if unread_ids:
        Notification.query.filter(Notification.id.in_(unread_ids)).update(
            {'is_read': True}, synchronize_session=False,
        )
        db.session.commit()
    return html


@bp.route('/<int:nid>/buka')
@login_required
def buka(nid):
    """Tandai dibaca lalu buka tautan notifikasi (hanya milik sendiri)."""
    n = Notification.query.filter_by(id=nid, user_id=current_user.id).first_or_404()
    n.is_read = True
    db.session.commit()
    link = n.link or ''
    if link.startswith('/') and not link.startswith('//'):
        return redirect(link)
    return redirect(url_for('notifikasi.index'))


@bp.route('/baca-semua', methods=['POST'])
@login_required
def baca_semua():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update(
        {'is_read': True}, synchronize_session=False,
    )
    db.session.commit()
    nxt = request.form.get('next', '')
    return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else url_for('notifikasi.index'))
