"""Buku alamat: satu akun bisa menyimpan beberapa alamat pengiriman."""
from datetime import UTC, datetime

from app import db

ADDRESS_LABELS = [('rumah', 'Rumah'), ('kantor', 'Kantor'), ('kos', 'Kos')]
ADDRESS_FIELDS = (
    'recipient_name', 'phone', 'address', 'address_label', 'district',
    'city', 'province', 'postal_code', 'delivery_note',
)
MAX_ADDRESSES = 10


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class Address(db.Model):
    __tablename__ = 'addresses'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_name = db.Column(db.String(200), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    address_label = db.Column(db.String(20), nullable=False, default='rumah')
    district = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    province = db.Column(db.String(100), nullable=False)
    postal_code = db.Column(db.String(10), nullable=False)
    delivery_note = db.Column(db.String(300), nullable=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    @property
    def label_text(self):
        return dict(ADDRESS_LABELS).get(self.address_label, (self.address_label or '').title())


def user_addresses(user):
    """Alamat milik user (utama dulu). Alamat lama di tabel users dipindahkan otomatis."""
    rows = (
        Address.query.filter_by(user_id=user.id)
        .order_by(Address.is_default.desc(), Address.created_at.asc(), Address.id.asc())
        .all()
    )
    if not rows and user.has_shipping_details:
        legacy = Address(user_id=user.id, is_default=True, **{
            f: (getattr(user, f) or '').strip() or None for f in ADDRESS_FIELDS
        })
        legacy.address_label = user.address_label or 'rumah'
        db.session.add(legacy)
        db.session.commit()
        rows = [legacy]
    return rows


def sync_user_default(user, address):
    """Salin alamat utama ke kolom users (dipakai checkout lama & tarif ongkir)."""
    for f in ADDRESS_FIELDS:
        setattr(user, f, getattr(address, f) if address else None)
    if address is None:
        user.address_label = 'rumah'


def set_default(user, address):
    Address.query.filter(Address.user_id == user.id, Address.id != address.id).update(
        {'is_default': False}, synchronize_session=False,
    )
    address.is_default = True
    sync_user_default(user, address)
