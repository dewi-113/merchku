import hashlib
from datetime import UTC, datetime

from flask_login import UserMixin

from app import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='customer')  # admin/seller/customer
    shop_name = db.Column(db.String(120), nullable=True)
    shop_description = db.Column(db.Text, nullable=True)
    recipient_name = db.Column(db.String(200), nullable=True)
    address = db.Column(db.Text, nullable=True)
    address_label = db.Column(db.String(20), nullable=False, default='rumah')
    district = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    postal_code = db.Column(db.String(10), nullable=True)
    province = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(30), nullable=True)
    delivery_note = db.Column(db.String(300), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    avatar = db.Column(db.String(255), nullable=True)
    failed_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=_utcnow)
    updated_at = db.Column(db.DateTime, default=_utcnow, onupdate=_utcnow)

    def session_fingerprint(self):
        """Sidik jari dari hash password. Berubah saat password diganti, sehingga
        semua sesi & cookie "ingat saya" lama otomatis tidak berlaku."""
        return hashlib.sha256((self.password_hash or '').encode()).hexdigest()[:16]

    def get_id(self):
        return f'{self.id}:{self.session_fingerprint()}'

    @property
    def is_seller(self):
        return self.role in ('seller', 'admin')

    @property
    def has_shipping_details(self):
        required = (
            self.recipient_name,
            self.address,
            self.district,
            self.city,
            self.postal_code,
            self.province,
            self.phone,
        )
        return all(value and value.strip() for value in required)

    def __repr__(self):
        return f'<User {self.email}>'
