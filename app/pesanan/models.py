from datetime import UTC, datetime

from app import db

# ---------- konstanta status ----------

ORDER_STATUSES = [
    'menunggu_pembayaran',
    'menunggu_verifikasi',
    'dibayar',
    'ditolak',
    'dikirim',
    'selesai',
    'dibatalkan',
]

# Transisi yang diizinkan: {status_asal: [status_tujuan, ...]}
VALID_TRANSITIONS = {
    # 'dibayar' dari menunggu_pembayaran/ditolak = konfirmasi manual oleh
    # penjual/admin (mis. dana sudah masuk tapi pembeli belum unggah bukti).
    'menunggu_pembayaran':  ['menunggu_verifikasi', 'dibayar', 'dibatalkan'],
    'menunggu_verifikasi':  ['dibayar', 'ditolak'],
    'dibayar':              ['dikirim'],
    'ditolak':              ['menunggu_pembayaran', 'menunggu_verifikasi', 'dibayar', 'dibatalkan'],
    'dikirim':              ['selesai'],
    'selesai':              [],
    'dibatalkan':           [],
}

COD_TRANSITIONS = {
    'menunggu_pembayaran': ['dibayar', 'dibatalkan'],
}

COURIER_LABELS = {
    'jne': 'JNE',
    'jnt': 'J&T Express',
    'sicepat': 'SiCepat',
    'anteraja': 'AnterAja',
    'pos': 'Pos Indonesia',
}

PAYMENT_METHOD_LABELS = {
    'bank_transfer': 'Transfer Bank',
    'qris': 'QRIS',
    'ewallet': 'E-Wallet',
    'cod': 'Tunai saat pesanan diterima (COD)',
    'midtrans': 'Pembayaran Online (Midtrans)',
}

# Status yang boleh dibatalkan oleh customer sendiri
CUSTOMER_CANCELLABLE = {'menunggu_pembayaran', 'ditolak'}

# Status saat stok produk masih "di-reserve" oleh pesanan: stok sudah
# dikurangi saat checkout, tapi belum berpindah ke pembeli. Kalau pesanan
# dibatalkan pada status ini, stok HARUS dikembalikan.
STOCK_RESERVED_STATUSES = {'menunggu_pembayaran', 'menunggu_verifikasi', 'ditolak'}

# Status saat customer boleh mengunggah bukti bayar.
# 'ditolak' ikut diperbolehkan supaya customer bisa mengunggah ulang bukti
# setelah pembayaran ditolak admin (bukan terkunci selamanya).
BUKTI_UPLOAD_ALLOWED = {'menunggu_pembayaran', 'ditolak'}


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def restore_reserved_stock(order):
    """Kembalikan stok produk yang direserve oleh sebuah pesanan.

    Dipakai saat pesanan dibatalkan sebelum dibayar (oleh customer maupun admin).
    Stok dikembalikan ke produk asal, atau ke stok per ukuran sesuai snapshot pesanan.

    Mengembalikan jumlah unit stok yang dikembalikan.
    """
    from sqlalchemy import select

    from app.katalog.models import Product, ProductSizeStock

    restored = 0
    for oi in order.items:
        product = db.session.execute(
            select(Product)
            .where(Product.id == oi.product_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not product:
            continue

        if product.use_sizes and oi.size:
            ss = db.session.execute(
                select(ProductSizeStock)
                .where(
                    ProductSizeStock.product_id == product.id,
                    ProductSizeStock.size == oi.size,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if ss:
                ss.stock += oi.quantity
                restored += oi.quantity
        else:
            product.stock = (product.stock or 0) + oi.quantity
            restored += oi.quantity

    return restored


# ---------- model ----------

class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default='menunggu_pembayaran', index=True)

    # Alamat pengiriman (snapshot saat checkout, bukan FK ke tabel address)
    recipient_name = db.Column(db.String(200), nullable=False)
    address = db.Column(db.Text, nullable=False)
    address_label = db.Column(db.String(20), nullable=False, default='rumah')
    district = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)
    province = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), nullable=False)
    delivery_note = db.Column(db.String(300), nullable=True)
    courier = db.Column(db.String(20), nullable=False, default='jne')
    shipping_service = db.Column(db.String(100), nullable=True)
    shipping_duration = db.Column(db.String(100), nullable=True)
    shipping_cost = db.Column(db.Integer, nullable=False, default=0)
    shipping_discount = db.Column(db.Integer, nullable=False, default=0)
    service_fee = db.Column(db.Integer, nullable=False, default=0)
    fragile_protection = db.Column(db.Boolean, nullable=False, default=False)
    fragile_fee = db.Column(db.Integer, nullable=False, default=0)
    payment_method = db.Column(db.String(30), nullable=False, default='bank_transfer')
    payment_transaction_id = db.Column(db.String(100), nullable=True, unique=True)
    payment_token = db.Column(db.String(255), nullable=True)
    payment_redirect_url = db.Column(db.String(500), nullable=True)

    # Total dihitung di server saat checkout, disimpan untuk audit
    total_price = db.Column(db.Integer, nullable=False)  # rupiah

    # Bukti bayar (nama file di uploads/private)
    payment_proof = db.Column(db.String(255), nullable=True)

    # Catatan admin saat approve/reject
    admin_note = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    items = db.relationship('OrderItem', backref='order', lazy='selectin',
                            cascade='all, delete-orphan')
    user = db.relationship('User', lazy='joined')

    def can_transition_to(self, new_status: str) -> bool:
        return new_status in self.allowed_transitions

    @property
    def allowed_transitions(self):
        if self.payment_method == 'cod':
            return COD_TRANSITIONS.get(self.status, VALID_TRANSITIONS.get(self.status, []))
        return VALID_TRANSITIONS.get(self.status, [])

    @property
    def display_status(self):
        if self.payment_method == 'cod':
            if self.status == 'menunggu_pembayaran':
                return 'menunggu_konfirmasi_cod'
            if self.status == 'dibayar':
                return 'cod_dikonfirmasi'
        return self.status

    @property
    def courier_label(self):
        return COURIER_LABELS.get(self.courier, self.courier or '-')

    @property
    def total_products(self):
        return sum(item.subtotal for item in self.items)

    @property
    def payment_method_label(self):
        return PAYMENT_METHOD_LABELS.get(self.payment_method, self.payment_method or '-')

    def __repr__(self):
        return f'<Order id={self.id} user={self.user_id} status={self.status}>'


class OrderItem(db.Model):
    __tablename__ = 'order_items'

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'),
                         nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    product_name = db.Column(db.String(200), nullable=False)  # snapshot nama saat checkout
    product_description = db.Column(db.Text, nullable=True)
    product_type = db.Column(db.String(100), nullable=True)
    product_color = db.Column(db.String(80), nullable=True)
    size = db.Column(db.String(10), nullable=True)            # snapshot ukuran
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Integer, nullable=False)        # snapshot harga saat checkout (rupiah)

    product = db.relationship('Product', lazy='joined')

    @property
    def subtotal(self):
        return self.unit_price * self.quantity

    def __repr__(self):
        return f'<OrderItem order={self.order_id} product={self.product_id} qty={self.quantity}>'
