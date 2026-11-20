"""Data grafik pendapatan harian untuk dashboard penjual & admin."""
from datetime import UTC, datetime, timedelta

from app import db

BULAN = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']


def _paid_filter():
    """Uang yang sudah diterima: non-COD sejak dibayar, COD saat selesai."""
    from app.katalog.stats import SOLD_STATUSES
    from app.pesanan.models import Order

    return db.or_(
        db.and_(Order.payment_method != 'cod', Order.status.in_(SOLD_STATUSES)),
        db.and_(Order.payment_method == 'cod', Order.status == 'selesai'),
    )


def daily_revenue(days=14, seller_id=None):
    """[{'date', 'label', 'value'}] untuk `days` hari terakhir (termasuk hari ini).

    seller_id=None  -> omzet seluruh pesanan (admin, total pesanan).
    seller_id=<id>  -> hanya subtotal produk milik penjual tersebut.
    """
    from app.katalog.models import Product
    from app.pesanan.models import Order, OrderItem

    today = datetime.now(UTC).date()
    start = today - timedelta(days=days - 1)
    since = datetime.combine(start, datetime.min.time())

    if seller_id is None:
        rows = (
            db.session.query(Order.created_at, Order.total_price)
            .filter(_paid_filter(), Order.created_at >= since)
            .all()
        )
    else:
        rows = (
            db.session.query(Order.created_at, OrderItem.quantity * OrderItem.unit_price)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .join(Product, Product.id == OrderItem.product_id)
            .filter(_paid_filter(), Order.created_at >= since, Product.owner_id == seller_id)
            .all()
        )

    totals = {start + timedelta(days=i): 0 for i in range(days)}
    for created_at, amount in rows:
        if created_at and created_at.date() in totals:
            totals[created_at.date()] += int(amount or 0)

    series = [
        {'date': d, 'label': f'{d.day} {BULAN[d.month - 1]}', 'value': v}
        for d, v in sorted(totals.items())
    ]
    peak = max((p['value'] for p in series), default=0)
    total = sum(p['value'] for p in series)
    return {'points': series, 'peak': peak, 'total': total, 'days': days}
