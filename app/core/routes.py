import hashlib
import os
import re

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    redirect,
    request,
    send_from_directory,
    url_for,
)

from app import db
from app.core.utils import get_client_ip
from app.security_logger import sec_log

_UUID_FILE = re.compile(r'^[0-9a-f]{32}\.jpg$')
_PHOTO_MAX_SIZE = (900, 1100)

# Nama dasar folder foto di PRODUCT_PHOTOS_DIR. Folder boleh bernama persis
# ("Hoodie"), hasil unduhan Google Drive ("Hoodie-20261022T134752Z-1-001"),
# dan boleh berisi subfolder bernama sama ("Hoodie/Hoodie").
_PRODUCT_PHOTO_FOLDERS = {
    'almet': 'Almet',
    'hoodie': 'Hoodie',
    'jaket': 'Jaket',
    'kaos_pendek': 'Kaos lengan pendek',
    'kaos_panjang': 'Kaos lengan panjang',
    'lanyard': 'Lanyard',
    'mug': 'Mug kampus',
    'notebook': 'Notebook a5',
    'pin': 'Pin',
    'stiker': 'Stiker',
    'topi': 'Topi',
    'totebag': 'Totebag',
    'gantungan_kunci': 'Gantungan kunci',
}

bp = Blueprint('core', __name__)


@bp.get('/logo')
def logo():
    """Sajikan logo aplikasi dari folder app/logo."""
    directory = os.path.join(current_app.root_path, 'logo')
    for name in ('logo merchku.png', 'logo_merchku.png', 'logo.png'):
        if os.path.exists(os.path.join(directory, name)):
            return send_from_directory(directory, name)
    return abort(404)


@bp.get('/video')
def video():
    """Sajikan video latar dari folder app/video."""
    directory = os.path.join(current_app.root_path, 'video')
    if not os.path.isdir(directory):
        return abort(404)
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(('.mp4', '.webm', '.ogg')):
            return send_from_directory(
                directory, name, conditional=True, mimetype='video/mp4'
            )
    return abort(404)


@bp.get('/')
def landing():
    """Landing page publik."""
    from flask import render_template

    from app.auth.models import User
    from app.katalog.models import Product

    demo_seller = User.query.filter_by(email='seller@demo.test').first()
    featured_query = Product.query.filter_by(is_active=True)
    if demo_seller:
        demo_products = (
            featured_query.filter_by(owner_id=demo_seller.id)
            .order_by(Product.created_at.desc())
            .limit(8)
            .all()
        )
        featured = demo_products or (
            featured_query.order_by(Product.created_at.desc()).limit(8).all()
        )
    else:
        featured = featured_query.order_by(Product.created_at.desc()).limit(8).all()


    # Toko yang punya produk aktif, diurutkan dari produk terbanyak
    shop_rows = (
        db.session.query(User, db.func.count(Product.id))
        .join(Product, Product.owner_id == User.id)
        .filter(Product.is_active.is_(True), User.role.in_(('seller', 'admin')))
        .group_by(User.id)
        .order_by(db.func.count(Product.id).desc())
        .limit(6)
        .all()
    )
    shops = [
        {
            'seller': seller,
            'product_count': count,
            'products': (
                featured_query.filter_by(owner_id=seller.id)
                .order_by(Product.created_at.desc()).limit(3).all()
            ),
        }
        for seller, count in shop_rows
    ]

    from app.katalog.stats import best_seller_ids

    top_ids = best_seller_ids(10)
    top_products = {p.id: p for p in Product.query.filter(Product.id.in_(top_ids)).all()} if top_ids else {}
    bestsellers = [top_products[pid] for pid in top_ids if pid in top_products]
    # Rekomendasi: produk pilihan toko utama dulu, lalu produk terbaru dari semua toko
    featured_ids = [p.id for p in featured]
    others_query = featured_query
    if featured_ids:
        others_query = others_query.filter(Product.id.notin_(featured_ids))
    others = (
        others_query.order_by(Product.created_at.desc(), Product.id.desc())
        .limit(30 - len(featured))
        .all()
    )
    # Selang-seling agar produk dari berbagai toko bercampur seperti feed marketplace
    recommended = []
    for index in range(max(len(featured), len(others))):
        recommended += featured[index:index + 1] + others[index:index + 1]
    # Produk diskon: punya harga coret lebih tinggi dari harga jual
    discount_ratio = db.cast(Product.price, db.Float) / Product.original_price
    discounted = (
        featured_query.filter(Product.original_price > Product.price)
        .order_by(discount_ratio.asc(), Product.id.desc())
        .limit(12)
        .all()
    )
    max_discount = max((p.discount_percent for p in discounted), default=0)
    return render_template(
        'core/landing.html', featured=featured, shops=shops,
        bestsellers=bestsellers, recommended=recommended,
        discounted=discounted, max_discount=max_discount,
    )


@bp.get('/healthz')
def healthz():
    ok = True
    try:
        db.session.execute(db.text('SELECT 1'))
    except Exception:
        ok = False
    return jsonify({'status': 'ok' if ok else 'degraded', 'db': ok}), 200


@bp.get('/metrics')
def metrics():
    token = request.args.get('token') or request.headers.get('X-Metrics-Token')
    if token != current_app.config.get('METRICS_TOKEN') or not token:
        sec_log(
            event='access_denied',
            ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
            path='/metrics', method='GET', resource='metrics',
        )
        abort(403)

    from flask import Response
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Gauge,
        generate_latest,
    )

    registry = CollectorRegistry()

    # ── Gauge domain ────────────────────────────────────────────────
    from app.auth.models import User
    from app.katalog.models import Product
    from app.pesanan.models import ORDER_STATUSES, Order

    try:
        # Jumlah user
        g_users = Gauge('merchku_users_total', 'Total registered users', registry=registry)
        g_users.set(db.session.query(db.func.count(User.id)).scalar() or 0)

        # Jumlah produk aktif / total
        g_prod_total = Gauge('merchku_products_total', 'Total products', registry=registry)
        g_prod_active = Gauge('merchku_products_active', 'Active products', registry=registry)
        g_prod_total.set(db.session.query(db.func.count(Product.id)).scalar() or 0)
        g_prod_active.set(
            db.session.query(db.func.count(Product.id))
            .filter(Product.is_active.is_(True))
            .scalar()
            or 0
        )

        # Pesanan per status
        g_orders = Gauge(
            'merchku_orders_by_status', 'Orders by status',
            ['status'], registry=registry,
        )
        for status in ORDER_STATUSES:
            count = (
                db.session.query(db.func.count(Order.id))
                .filter(Order.status == status)
                .scalar() or 0
            )
            g_orders.labels(status=status).set(count)

    except Exception as exc:
        sec_log(event='server_error', path='/metrics', detail=str(exc))

    data = generate_latest(registry)
    return Response(data, mimetype=CONTENT_TYPE_LATEST)


@bp.get('/media/produk/<path:filename>')
def produk_media(filename):
    """Sajikan gambar produk publik. Hanya nama file UUID.jpg yang valid."""
    if not _UUID_FILE.match(filename):
        sec_log(
            event='suspicious_request', level='warning',
            ip=get_client_ip(current_app.config.get('TRUSTED_PROXIES')),
            path=request.path, method=request.method, pattern='path_traversal',
        )
        abort(404)
    directory = current_app.config['UPLOAD_PUBLIC']
    if not os.path.exists(os.path.join(directory, filename)):
        abort(404)
    resp = send_from_directory(directory, filename)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@bp.get('/media/produk-foto/<int:product_id>')
def produk_foto(product_id):
    """Sajikan foto manual dari folder produk atau ilustrasi kategori."""
    from app.katalog.models import Product

    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)

    directory = current_app.config['PRODUCT_PHOTOS_DIR']
    for extension in ('.jpg', '.jpeg', '.png'):
        filename = f'product-{product.id}{extension}'
        if os.path.isfile(os.path.join(directory, filename)):
            return _send_product_photo(directory, filename)

    photo_folder = _product_photo_folder(product)
    photo_directory = resolve_photo_directory(directory, photo_folder) if photo_folder else None
    photos = list_photos(photo_directory) if photo_directory else []
    if photos:
        photo_ids = [
            matching_product.id for matching_product in (
                Product.query.filter_by(category=product.category)
                .order_by(Product.id)
                .all()
            )
            if _product_photo_folder(matching_product) == photo_folder
        ]
        photo_index = photo_ids.index(product.id) % len(photos)
        return _send_product_photo(photo_directory, photos[photo_index])

    if product.category == 'kaos':
        image_name = 'tshirt.svg'
    elif product.category == 'hoodie':
        image_name = 'hoodie.svg'
    elif product.category in ('jaket', 'almet'):
        image_name = 'jacket.svg'
    elif product.category == 'stiker':
        image_name = 'stickers.svg'
    elif product.category == 'lanyard':
        image_name = 'lanyard.svg'
    elif 'topi' in product.name.lower():
        image_name = 'cap.svg'
    else:
        image_name = 'accessories.svg'
    return redirect(url_for('static', filename=f'images/demo/{image_name}'))


@bp.get('/media/kategori/<key>')
def kategori_foto(key):
    """Ikon kategori dari foto produk asli (dipotong kotak)."""
    base_name = _PRODUCT_PHOTO_FOLDERS.get(key)
    if base_name is None:
        abort(404)
    directory = resolve_photo_directory(current_app.config['PRODUCT_PHOTOS_DIR'], base_name)
    photos = list_photos(directory) if directory else []
    if not photos:
        return redirect(url_for('static', filename='images/demo/accessories.svg'))
    return _send_product_photo(directory, photos[0], square=True)


def list_photos(directory):
    """Daftar file foto (jpg/png) di sebuah folder, terurut tanpa peduli huruf besar."""
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return sorted(
        (
            name for name in names
            if name.lower().endswith(('.jpg', '.jpeg', '.png'))
            and os.path.isfile(os.path.join(directory, name))
        ),
        key=str.casefold,
    )


def resolve_photo_directory(root, base_name):
    """Cari folder foto untuk nama dasar tertentu, toleran terhadap variasi nama."""
    key = base_name.casefold()

    def matches(name):
        name = name.casefold()
        return name == key or name.startswith((f'{key}-', f'{key} -'))

    def subdirs(path):
        try:
            return sorted(
                (entry for entry in os.listdir(path) if os.path.isdir(os.path.join(path, entry))),
                key=str.casefold,
            )
        except OSError:
            return []

    # Cek folder level atas yang cocok, lalu subfolder yang cocok (mis. "Notebook/Notebook a5").
    for entry in subdirs(root):
        top = os.path.join(root, entry)
        candidates = [top] if matches(entry) else []
        candidates += [os.path.join(top, child) for child in subdirs(top) if matches(child)]
        for candidate in candidates:
            if list_photos(candidate):
                return candidate
    return None


def _send_product_photo(directory, filename, square=False):
    """Kirim foto produk dalam versi JPEG yang sudah diperkecil.

    Foto asli di folder produk berukuran ±4 MB (PNG 1760px) sehingga sangat
    berat untuk HP. Versi kecil dibuat sekali lalu disimpan di instance/
    photo_cache; bila gagal, file asli tetap dikirim. ``square=True`` memotong
    bagian produk (tengah-bawah poster) menjadi kotak untuk ikon kategori.
    """
    source = os.path.join(directory, filename)
    cache_dir = os.path.join(current_app.instance_path, 'photo_cache')
    try:
        stat = os.stat(source)
        mode = 'square' if square else _PHOTO_MAX_SIZE
        key = hashlib.sha1(
            f'{source}|{stat.st_mtime_ns}|{stat.st_size}|{mode}'.encode(),
            usedforsecurity=False,  # hanya nama file cache
        ).hexdigest()
        cached_name = f'{key}.jpg'
        cached_path = os.path.join(cache_dir, cached_name)
        if not os.path.isfile(cached_path):
            from PIL import Image

            os.makedirs(cache_dir, exist_ok=True)
            with Image.open(source) as image:
                image = image.convert('RGBA')
                background = Image.new('RGB', image.size, (255, 255, 255))
                background.paste(image, mask=image.getchannel('A'))
                if square:
                    width, height = background.size
                    side = int(min(width, height) * 0.72)
                    top = min(int(height * 0.36), height - side)
                    left = (width - side) // 2
                    background = background.crop((left, top, left + side, top + side))
                    background = background.resize((240, 240), Image.LANCZOS)
                else:
                    background.thumbnail(_PHOTO_MAX_SIZE)
                temp_path = f'{cached_path}.{os.getpid()}.tmp'
                background.save(temp_path, 'JPEG', quality=82, optimize=True, progressive=True)
                os.replace(temp_path, cached_path)
        response = send_from_directory(cache_dir, cached_name, conditional=True, max_age=86400)
    except Exception:
        response = send_from_directory(directory, filename, conditional=True)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


def _product_photo_folder(product):
    name = product.name.casefold()
    if product.category == 'almet':
        return _PRODUCT_PHOTO_FOLDERS['almet']
    if product.category == 'hoodie':
        return _PRODUCT_PHOTO_FOLDERS['hoodie']
    if product.category == 'jaket':
        return _PRODUCT_PHOTO_FOLDERS['jaket']
    if product.category == 'kaos':
        sleeve = 'panjang' if 'panjang' in name else 'pendek'
        return _PRODUCT_PHOTO_FOLDERS[f'kaos_{sleeve}']
    if product.category == 'stiker':
        return _PRODUCT_PHOTO_FOLDERS['stiker']
    if product.category == 'lanyard':
        return _PRODUCT_PHOTO_FOLDERS['lanyard']
    if product.category == 'tote_bag':
        return _PRODUCT_PHOTO_FOLDERS['totebag']
    if 'pin' in name:
        return _PRODUCT_PHOTO_FOLDERS['pin']
    if 'mug' in name:
        return _PRODUCT_PHOTO_FOLDERS['mug']
    if 'notebook' in name:
        return _PRODUCT_PHOTO_FOLDERS['notebook']
    if 'topi' in name:
        return _PRODUCT_PHOTO_FOLDERS['topi']
    if 'gantungan kunci' in name:
        return _PRODUCT_PHOTO_FOLDERS['gantungan_kunci']
    return None


@bp.get('/media/avatar/<path:filename>')
def avatar_media(filename):
    """Sajikan gambar avatar publik. Hanya nama file UUID.jpg yang valid."""
    if not _UUID_FILE.match(filename):
        abort(404)
    directory = current_app.config['UPLOAD_PUBLIC']
    if not os.path.exists(os.path.join(directory, filename)):
        abort(404)
    resp = send_from_directory(directory, filename)
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp
