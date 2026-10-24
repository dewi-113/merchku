from datetime import UTC, datetime

from app import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class ChatThread(db.Model):
    __tablename__ = 'chat_threads'

    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    customer = db.relationship('User', foreign_keys=[customer_id], lazy='joined')
    seller = db.relationship('User', foreign_keys=[seller_id], lazy='joined')
    messages = db.relationship(
        'ChatMessage',
        backref='thread',
        lazy='selectin',
        cascade='all, delete-orphan',
        order_by='ChatMessage.created_at',
    )

    __table_args__ = (
        db.UniqueConstraint('customer_id', 'seller_id', name='uq_chat_customer_seller'),
    )


class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(
        db.Integer,
        db.ForeignKey('chat_threads.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    sender = db.relationship('User', lazy='joined')
