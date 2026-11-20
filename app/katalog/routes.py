import re

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db, limiter
from app.core.utils import get_client_ip
from app.katalog.follow_model import ShopFollow, follower_counts
from app.katalog.forms import ReviewForm
from app.katalog.models import CATEGORIES, Product
from app.katalog.review_model import Review
from app.pesanan.models import Order, OrderItem
from app.security_logger import sec_log

bp = Blueprint('katalog', __name__, url_prefix='/katalog')

CAT_RE = re.compile(r'^(almet|kaos|hoodie|jaket|stiker|lanyard|tote_bag|lainnya)$')
SORT_ALLOWED = {'terbaru', 'termurah', 'termahal', 'populer', 'terlaris', 'diskon'}


def _log(event, **kw):
    """Helper log dengan konteks request/user.

    Nilai default hanya dipakai bila pemanggil tidak menyediakannya sendiri,
    sehingga pemanggil boleh meng-override (mis. `user_id`) tanpa error.
    """
    level = kw.pop('level', None)  # None: sec_log memilih info/warning sesuai event
    kw.setdefault('ip', get_client_ip(current_app.config.get('TRUSTED_PROXIES')))
    kw.setdefault('path', request.path)
    kw.setdefault('method', request.method)
    kw.setdefault('user_id', getattr(current_user, 'id', None))
    kw.setdefault('email', getattr(current_user, 'email', None))
    kw.setdefault('role', getattr(current_user, 'role', None))
    sec_log(event=event, level=level, **kw)


def _has_completed_purchase(user_id, product_id):
    return (
        db.session.query(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            Order.user_id == user_id,
            Order.status == 'selesai',
            OrderItem.product_id == product_id,
        )
        .first()
        is not None
    )


@bp.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    cat = (request.args.get('cat') or '').strip()
    minp = request.args.get('minp', type=int)
    maxp = request.args.get('maxp', type=int)
    sort = (request.args.get('sort') or 'terbaru').strip()

    if sort not in SORT_ALLOWED:
        sort = 'terbaru'
    if minp is not None and minp < 0:
        minp = 0
    if maxp is not None and maxp < 0:
        maxp = None
    if minp is not None and maxp is not None and minp > maxp:
        minp, maxp = maxp, minp

    query = Product.query.filter_by(is_active=True)
    if q:
        like = f'%{q}%'
        query = query.filter(db.or_(Product.name.ilike(like), Product.description.ilike(like)))
    if cat and CAT_RE.match(cat):
        query = query.filter(Product.category == cat)
    if minp is not None:
        query = query.filter(Product.price >= minp)
    if maxp is not None:
        query = query.filter(Product.price <= maxp)
    if sort == 'termurah':
        query = query.order_by(Product.price.asc())
    elif sort == 'termahal':
        query = query.order_by(Product.price.desc())
    elif sort == 'populer':
        # Paling banyak ulasan, lalu rating rata-rata, lalu yang terbaru.
        # Subquery korelasi dipakai agar tidak perlu GROUP BY (pagination aman).
        review_count = (
            db.session.query(db.func.count(Review.id))
            .filter(Review.product_id == Product.id)
            .correlate(Product)
            .scalar_subquery()
        )
        avg_rating = (
            db.session.query(db.func.avg(Review.rating))
            .filter(Review.product_id == Product.id)
            .correlate(Product)
            .scalar_subquery()
        )
        query = query.order_by(
            review_count.desc(), avg_rating.desc(), Product.created_at.desc()
        )
    elif sort == 'diskon':
        discount_ratio = db.cast(Product.price, db.Float) / Product.original_price
        query = query.filter(Product.original_price > Product.price).order_by(
            discount_ratio.asc(), Product.created_at.desc()
        )
    elif sort == 'terlaris':
        from app.katalog.stats import SOLD_STATUSES

        sold = (
            db.session.query(db.func.coalesce(db.func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(OrderItem.product_id == Product.id, Order.status.in_(SOLD_STATUSES))
            .correlate(Product)
            .scalar_subquery()
        )
        query = query.order_by(sold.desc(), Product.created_at.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    pagination = query.paginate(page=page, per_page=12, error_out=False)
    pagination_params = request.args.to_dict(flat=True)
    pagination_params.pop('page', None)
    return render_template(
        'katalog/index.html',
        pagination=pagination,
        categories=CATEGORIES,
        params=request.args,
        pagination_params=pagination_params,
    )


@bp.route('/<int:pid>', methods=['GET', 'POST'])
@limiter.limit('3 per hour', key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr, methods=['POST'])
def detail(pid):
    p = db.session.get(Product, pid)
    if not p or not p.is_active:
        abort(404)
    form = ReviewForm()
    existing_review = None
    can_review = False
    if current_user.is_authenticated:
        existing_review = Review.query.filter_by(product_id=p.id, user_id=current_user.id).first()
        can_review = (
            current_user.role == 'customer'
            and _has_completed_purchase(current_user.id, p.id)
        )

    if request.method == 'POST':
        if not current_user.is_authenticated:
            _log('access_denied', level='warning', resource='review', resource_id=pid)
            abort(403)
        if existing_review:
            flash('Anda sudah memberikan ulasan untuk produk ini.', 'warning')
            return redirect(url_for('katalog.detail', pid=p.id))
        if not can_review:
            flash('Ulasan hanya dapat diberikan setelah pesanan produk selesai.', 'warning')
            return redirect(url_for('katalog.detail', pid=p.id))
        if form.validate_on_submit():
            rating = int(form.rating.data)
            if rating < 1 or rating > 5:
                flash('Rating tidak valid.', 'danger')
                return redirect(url_for('katalog.detail', pid=p.id))
            comment = (form.comment.data or '').strip()
            try:
                rev = Review(product_id=p.id, user_id=current_user.id,
                             rating=rating, comment=comment or None)
                db.session.add(rev)
                db.session.commit()
            except Exception:
                db.session.rollback()
                flash('Terjadi kesalahan saat menyimpan ulasan.', 'danger')
                return redirect(url_for('katalog.detail', pid=p.id))
            _log('review_created', product_id=p.id, user_id=current_user.id, rating=rating)
            flash('Terima kasih atas ulasan Anda.', 'success')
            return redirect(url_for('katalog.detail', pid=p.id))
        else:
            flash('Data ulasan tidak valid.', 'danger')
            return redirect(url_for('katalog.detail', pid=p.id))

    reviews = Review.query.filter_by(product_id=p.id).order_by(Review.created_at.desc()).limit(100).all()
    avg = db.session.query(db.func.avg(Review.rating)).filter(Review.product_id == p.id).scalar() or 0.0
    size_stocks = []
    if p.use_sizes and p.stock_sizes:
        size_stocks = sorted(p.stock_sizes, key=lambda s: {'S':0,'M':1,'L':2,'XL':3,'XXL':4}.get(s.size, 99))
    recommendations = (
        Product.query.filter(
            Product.is_active.is_(True),
            Product.id != p.id,
        )
        .order_by(
            (Product.category == p.category).desc(),
            Product.created_at.desc(),
        )
        .limit(4)
        .all()
    )
    seller_stats = None
    if p.owner:
        seller_product_count = Product.query.filter_by(
            owner_id=p.owner.id,
            is_active=True,
        ).count()
        seller_stats = (
            db.session.query(
                db.func.count(Review.id),
                db.func.avg(Review.rating),
            )
            .join(Product, Product.id == Review.product_id)
            .filter(Product.owner_id == p.owner.id, Product.is_active.is_(True))
            .one()
        )
        seller_stats = {
            'followers': follower_counts([p.owner.id])[p.owner.id],
            'is_following': _is_following(p.owner.id),
            'product_count': seller_product_count,
            'review_count': seller_stats[0],
            'review_average': (
                f'{seller_stats[1]:.1f}' if seller_stats[1] else '0.0'
            ),
        }
    return render_template('katalog/detail.html', product=p, form=form,
                           reviews=reviews, existing_review=existing_review,
                           avg=f'{avg:.1f}', size_stocks=size_stocks,
                           can_review=can_review, recommendations=recommendations,
                           seller_stats=seller_stats)


@bp.route('/toko/<int:seller_id>')
def toko_public(seller_id):
    from app.auth.models import User

    seller = db.session.get(User, seller_id)
    if not seller or seller.role not in ('seller', 'admin'):
        abort(404)
    products = (
        Product.query.filter_by(owner_id=seller.id, is_active=True)
        .order_by(Product.created_at.desc())
        .all()
    )
    review_count, review_average = (
        db.session.query(
            db.func.count(Review.id),
            db.func.avg(Review.rating),
        )
        .join(Product, Product.id == Review.product_id)
        .filter(Product.owner_id == seller.id, Product.is_active.is_(True))
        .one()
    )
    from app.katalog.stats import SOLD_STATUSES

    sold_qty = db.func.sum(OrderItem.quantity)
    shop_sold = (
        db.session.query(db.func.coalesce(sold_qty, 0))
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Product.owner_id == seller.id, Order.status.in_(SOLD_STATUSES))
        .scalar()
    )
    orders_done = (
        db.session.query(db.func.count(db.func.distinct(Order.id)))
        .join(OrderItem, OrderItem.order_id == Order.id)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Product.owner_id == seller.id, Order.status == 'selesai')
        .scalar()
    )
    best_rows = (
        db.session.query(Product.id, sold_qty)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .filter(Product.owner_id == seller.id, Product.is_active.is_(True),
                Order.status.in_(SOLD_STATUSES))
        .group_by(Product.id)
        .order_by(sold_qty.desc())
        .limit(4)
        .all()
    )
    by_id = {p.id: p for p in products}
    best_sellers = [by_id[pid] for pid, _ in best_rows if pid in by_id]
    return render_template(
        'katalog/toko.html',
        seller=seller,
        products=products,
        best_sellers=best_sellers,
        shop_sold=int(shop_sold or 0),
        orders_done=int(orders_done or 0),
        review_count=review_count,
        review_average=f'{review_average:.1f}' if review_average else '0.0',
        followers=follower_counts([seller.id])[seller.id],
        is_following=_is_following(seller.id),
    )


def _is_following(seller_id):
    if not current_user.is_authenticated:
        return False
    return ShopFollow.query.filter_by(seller_id=seller_id, follower_id=current_user.id).first() is not None


@bp.route('/toko/<int:seller_id>/ikuti', methods=['POST'])
@limiter.limit('60 per hour')
@login_required
def toggle_follow(seller_id):
    """Ikuti / berhenti mengikuti toko. Hanya akun pembeli yang bisa mengikuti."""
    from app.auth.models import User

    seller = db.session.get(User, seller_id)
    if not seller or seller.role not in ('seller', 'admin'):
        abort(404)
    back = url_for('katalog.toko_public', seller_id=seller.id)
    if current_user.role != 'customer':
        flash('Hanya akun pembeli yang bisa mengikuti toko.', 'warning')
        return redirect(back)
    follow = ShopFollow.query.filter_by(seller_id=seller.id, follower_id=current_user.id).first()
    if follow:
        db.session.delete(follow)
        flash('Kamu berhenti mengikuti toko ini.', 'info')
    else:
        db.session.add(ShopFollow(seller_id=seller.id, follower_id=current_user.id))
        flash('Kamu sekarang mengikuti toko ini 🎉', 'success')
    db.session.commit()
    nxt = request.form.get('next', '')
    return redirect(nxt if nxt.startswith('/') and not nxt.startswith('//') else back)


@bp.route('/produk/<int:pid>/review', methods=['POST'])
@limiter.limit('3 per hour', key_func=lambda: get_client_ip(current_app.config.get('TRUSTED_PROXIES')) or request.remote_addr)
@login_required
def create_review_limited(pid):
    p = db.session.get(Product, pid)
    if not p or not p.is_active:
        abort(404)
    if current_user.role != 'customer' or not _has_completed_purchase(current_user.id, p.id):
        flash('Ulasan hanya dapat diberikan setelah pesanan produk selesai.', 'warning')
        return redirect(url_for('katalog.detail', pid=p.id))
    if Review.query.filter_by(product_id=p.id, user_id=current_user.id).first():
        flash('Sudah berulasan.', 'warning')
        return redirect(url_for('katalog.detail', pid=p.id))
    form = ReviewForm()
    if form.validate_on_submit():
        rating = int(form.rating.data)
        if rating < 1 or rating > 5:
            flash('Rating tidak valid.', 'danger')
            return redirect(url_for('katalog.detail', pid=p.id))
        try:
            rev = Review(product_id=p.id, user_id=current_user.id,
                         rating=rating, comment=(form.comment.data or '').strip() or None)
            db.session.add(rev)
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Terjadi kesalahan saat menyimpan ulasan.', 'danger')
            return redirect(url_for('katalog.detail', pid=p.id))
        _log('review_created', product_id=p.id, user_id=current_user.id, rating=rating)
        flash('Ulasan terkirim.', 'success')
    else:
        flash('Data ulasan tidak valid.', 'danger')
    return redirect(url_for('katalog.detail', pid=p.id))
