from datetime import UTC, datetime

from app import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)



class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text, nullable=True)
    seller_reply = db.Column(db.Text, nullable=True)
    replied_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    product = db.relationship('Product', backref=db.backref('reviews', lazy='dynamic', cascade='all, delete-orphan'))
    user = db.relationship('User', backref=db.backref('reviews', lazy='dynamic'))

    __table_args__ = (db.UniqueConstraint('product_id', 'user_id', name='uq_review_product_user'),)
