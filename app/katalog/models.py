from datetime import UTC, datetime

from app import db

SIZES = ['S', 'M', 'L', 'XL', 'XXL']
CATEGORIES = ['almet', 'kaos', 'hoodie', 'jaket', 'stiker', 'lanyard', 'tote_bag', 'lainnya']


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    description = db.Column(db.Text, default='')
    category = db.Column(db.String(50), nullable=False, default='lainnya', index=True)
    product_type = db.Column(db.String(100), nullable=True)
    color = db.Column(db.String(80), nullable=True)
    price = db.Column(db.Integer, nullable=False)  # rupiah, integer bulat
    # Harga coret (sebelum diskon). Opsional; `price` tetap harga yang ditagih.
    original_price = db.Column(db.Integer, nullable=True)
    weight_gram = db.Column(db.Integer, nullable=False, default=500)
    is_fragile = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, default=True, index=True)
    use_sizes = db.Column(db.Boolean, default=False)
    stock = db.Column(db.Integer, default=0)  # stok tunggal bila tidak pakai ukuran
    image = db.Column(db.String(255), nullable=True)  # nama file di uploads/public
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
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

    @property
    def discount_percent(self):
        """Persen diskon dari harga coret, 0 bila tidak ada diskon."""
        if not self.original_price or self.original_price <= self.price:
            return 0
        return round((1 - self.price / self.original_price) * 100)

    owner = db.relationship('User', lazy='joined')


class ProductSizeStock(db.Model):
    __tablename__ = 'product_size_stock'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False, index=True)
    size = db.Column(db.String(10), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (db.UniqueConstraint('product_id', 'size', name='uq_product_size'),)


def delete_or_archive_product(product, upload_dir):
    """Hapus produk, atau arsipkan (nonaktifkan) bila sudah pernah dipesan.

    Baris order_items menyimpan FK ke products, jadi produk yang sudah ada di
    riwayat pesanan tidak boleh dihapus permanen: di MySQL akan gagal karena
    foreign key, dan riwayat pesanan pembeli akan rusak. Return 'archived'
    atau 'deleted'.
    """
    import contextlib
    import os

    from app.keranjang.models import CartItem
    from app.pesanan.models import OrderItem

    if db.session.query(OrderItem.id).filter_by(product_id=product.id).first():
        product.is_active = False
        CartItem.query.filter_by(product_id=product.id).delete()
        db.session.commit()
        return 'archived'

    if product.image:
        with contextlib.suppress(OSError):
            os.remove(os.path.join(upload_dir, product.image))
    CartItem.query.filter_by(product_id=product.id).delete()
    db.session.delete(product)
    db.session.commit()
    return 'deleted'
