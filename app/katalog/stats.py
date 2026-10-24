"""Statistik ringkas produk (terjual & rating) untuk kartu produk.

Dihitung dengan dua query teragregasi sekaligus untuk semua produk yang
tampil, jadi tidak ada query per kartu (N+1).
"""
from app import db

# Pesanan yang dihitung sebagai "terjual": sudah dibayar sampai selesai.
SOLD_STATUSES = ('dibayar', 'dikirim', 'selesai')


def sold_label(count):
    """Format ala marketplace: 12, 1,2RB, 15RB."""
    if count < 1000:
        return str(count)
    value = count / 1000
    text = f'{value:.1f}'.rstrip('0').rstrip('.') if value < 10 else f'{int(value)}'
    return f"{text.replace('.', ',')}RB"


def reviewer_name(user):
    """Nama pengulas ala marketplace: "Rizky P." atau email tersamar "b***i"."""
    if user is None:
        return 'Pembeli'
    parts = (user.recipient_name or '').split()
    if parts:
        return f'{parts[0]} {parts[-1][0]}.' if len(parts) > 1 else parts[0]
    local = user.email.split('@')[0]
    return f'{local[0]}***{local[-1]}' if len(local) > 2 else f'{local[0]}***'


def product_stats(products):
    """Return {product_id: {'sold', 'sold_label', 'rating', 'reviews'}}."""
    from app.katalog.review_model import Review
    from app.pesanan.models import Order, OrderItem

    ids = [p.id if hasattr(p, 'id') else p for p in (products or [])]
    stats = {pid: {'sold': 0, 'sold_label': '0', 'rating': None, 'reviews': 0} for pid in ids}
    if not ids:
        return stats

    sold_rows = (
        db.session.query(OrderItem.product_id, db.func.coalesce(db.func.sum(OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .filter(OrderItem.product_id.in_(ids), Order.status.in_(SOLD_STATUSES))
        .group_by(OrderItem.product_id)
        .all()
    )
    for pid, sold in sold_rows:
        stats[pid]['sold'] = int(sold or 0)
        stats[pid]['sold_label'] = sold_label(int(sold or 0))

    review_rows = (
        db.session.query(Review.product_id, db.func.count(Review.id), db.func.avg(Review.rating))
        .filter(Review.product_id.in_(ids))
        .group_by(Review.product_id)
        .all()
    )
    for pid, count, average in review_rows:
        stats[pid]['reviews'] = int(count or 0)
        stats[pid]['rating'] = round(float(average), 1) if average else None
    return stats


def best_seller_ids(limit=10):
    """ID produk aktif dengan penjualan terbanyak (hanya yang pernah terjual)."""
    from app.katalog.models import Product
    from app.pesanan.models import Order, OrderItem

    total = db.func.sum(OrderItem.quantity)
    rows = (
        db.session.query(OrderItem.product_id, total)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Order.status.in_(SOLD_STATUSES), Product.is_active.is_(True))
        .group_by(OrderItem.product_id)
        .order_by(total.desc())
        .limit(limit)
        .all()
    )
    return [pid for pid, _ in rows]
