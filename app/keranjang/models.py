from datetime import UTC, datetime

from app import db

MAX_QTY_PER_ITEM = 99  # batas maksimum qty satu item keranjang


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class CartItem(db.Model):
    __tablename__ = 'cart_items'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False)
    size = db.Column(db.String(10), nullable=True)   # None bila produk tidak pakai ukuran
    quantity = db.Column(db.Integer, nullable=False, default=1)
    added_at = db.Column(db.DateTime, default=_utcnow)

    product = db.relationship('Product', lazy='joined')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'product_id', 'size', name='uq_cart_user_product_size'),
    )

    def __repr__(self):
        return f'<CartItem user={self.user_id} product={self.product_id} size={self.size} qty={self.quantity}>'
