from datetime import UTC, datetime

from app import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class ShopFollow(db.Model):
    """Pembeli yang mengikuti sebuah toko (penjual)."""
    __tablename__ = 'shop_follows'

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    follower_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=_utcnow)

    __table_args__ = (db.UniqueConstraint('seller_id', 'follower_id', name='uq_shop_follow'),)


def follower_counts(seller_ids):
    """{seller_id: jumlah pengikut} dalam satu query."""
    ids = list(seller_ids or [])
    counts = dict.fromkeys(ids, 0)
    if ids:
        rows = (
            db.session.query(ShopFollow.seller_id, db.func.count(ShopFollow.id))
            .filter(ShopFollow.seller_id.in_(ids))
            .group_by(ShopFollow.seller_id)
            .all()
        )
        counts.update({sid: int(n) for sid, n in rows})
    return counts
