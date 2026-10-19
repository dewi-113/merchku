import uuid as _uuid
from datetime import UTC, datetime

from app import db

SIZES = ['S', 'M', 'L', 'XL', 'XXL']
CATEGORIES = ['almet', 'kaos', 'hoodie', 'jaket', 'stiker', 'lanyard', 'tote_bag', 'lainnya']


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True, default=lambda: _uuid.uuid4().int & 0x7FFFFFFF)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(50), nullable=False, default='lainnya', index=True)
    price = db.Column(db.Integer, nullable=False)  # rupiah, integer bulat
    is_active = db.Column(db.Boolean, default=True, index=True)
    use_sizes = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Integer, default=0)  # stok tunggal bila tidak pakai ukuran
    image = db.Column(db.String(255), nullable=True)  # nama file di uploads/public
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, onupdate=_utcnow)

    stock_sizes = db.relationship(
        'ProductSizeStock', backref='product', lazy='selectin',
        cascade='all, delete-orphan',
    )

    @property
    def total_stock(self):
        if self.use_sizes:
            return sum(s.stock for s in self.stock_sizes)
        return self.stock or 0


class ProductSizeStock(db.Model):
    __tablename__ = 'product_size_stock'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    size = db.Column(db.String(10), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('product_id', 'size', name='uq_product_size'),)
