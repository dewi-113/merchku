"""Notifikasi di dalam aplikasi (ikon lonceng)."""
from datetime import UTC, datetime

from app import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    message = db.Column(db.String(300), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow, index=True)


def notify(user_id, message, link=None):
    """Tambahkan notifikasi (commit dilakukan oleh pemanggil)."""
    if user_id:
        db.session.add(Notification(user_id=user_id, message=message[:300], link=link))


def order_seller_ids(order):
    """ID penjual yang punya produk di pesanan ini."""
    return {it.product.owner_id for it in order.items if it.product and it.product.owner_id}


STATUS_MESSAGES = {
    'menunggu_verifikasi': 'sedang diverifikasi',
    'dibayar': 'pembayarannya dikonfirmasi dan sedang dikemas',
    'ditolak': 'bukti bayarnya ditolak, silakan unggah ulang',
    'dikirim': 'sedang dikirim',
    'selesai': 'selesai',
    'dibatalkan': 'dibatalkan',
}


def notify_buyer_status(order, new_status):
    """Beri tahu pembeli saat status pesanannya berubah."""
    from flask import url_for

    text = STATUS_MESSAGES.get(new_status)
    if not text:
        return
    if order.payment_method == 'cod' and new_status == 'dibayar':
        text = 'diterima penjual dan sedang dikemas (bayar tunai saat barang tiba)'
    msg = f'Pesanan #{order.id} {text}.'
    if new_status == 'dikirim' and order.tracking_number:
        msg = f'Pesanan #{order.id} sedang dikirim. No. resi: {order.tracking_number}.'
    notify(order.user_id, msg, url_for('pesanan.detail', order_id=order.id))


def notify_sellers(order, message):
    from flask import url_for

    for sid in order_seller_ids(order):
        notify(sid, message, url_for('seller.pesanan_detail', order_id=order.id))
