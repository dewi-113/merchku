"""
Regression test untuk bug yang pernah ditemukan di MERCHKU.

Setiap test di file ini mengunci perilaku yang sebelumnya salah, supaya
regresi tidak muncul lagi:

1. Helper `_log()` menerima `user_id` eksplisit tanpa TypeError (dulu 500).
2. Admin create/edit/hapus produk tidak lagi 500.
3. Admin cancel pesanan mengembalikan stok yang sudah di-reserve.
4. Customer cancel pesanan mengembalikan stok.
5. Rate limit register benar-benar bekerja (429 setelah melewati batas).
6. Validasi form produk: stok wajib diisi bila tidak pakai ukuran.
7. `sort=populer` diimplementasikan dan urut sesuai jumlah ulasan.
8. Login honoring `next=` (dan aman terhadap open redirect).
9. `Product.id`用的是 AUTO_INCREMENT, bukan ID acak.
10. URL gambar produk di form admin memakai route media, bukan `static/`.
11. `RATELIMIT_DEFAULT` diteruskan ke konfigurasi Flask-Limiter.
"""

import io
import tempfile

from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.katalog.review_model import Review
from app.keranjang.models import CartItem
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app


def _make_app(ratelimit=False):
    return create_test_app(
        RATELIMIT_ENABLED=ratelimit,
        UPLOAD_PRIVATE=tempfile.mkdtemp(),
        UPLOAD_PUBLIC=tempfile.mkdtemp(),
    )


def _seed(app):
    """Buat admin, customer, produk, dan pesanan menunggu pembayaran."""
    with app.app_context():
        db.drop_all()
        db.create_all()

        adm = User(
            email='adm@reg.test',
            password_hash=hash_password('Admin12345678'),
            role='admin',
            is_active=True,
        )
        cust = User(
            email='cust@reg.test',
            password_hash=hash_password('Cust12345678'),
            role='customer',
            is_active=True,
        )
        db.session.add_all([adm, cust])
        db.session.flush()

        p = Product(
            name='Kaos Reg',
            description='',
            category='kaos',
            price=50000,
            is_active=True,
            use_sizes=False,
            stock=10,
        )
        db.session.add(p)
        db.session.flush()

        order = Order(
            user_id=cust.id,
            status='menunggu_pembayaran',
            recipient_name='Reg',
            address='Jl. Reg',
            phone='081',
            total_price=50000,
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(
            OrderItem(
                order_id=order.id,
                product_id=p.id,
                product_name='Kaos Reg',
                size=None,
                quantity=2,
                unit_price=50000,
            )
        )
        db.session.flush()
        # Checkout mengurangi stok: 10 -> 8 (sisa setelah 2 unit dipesan).
        # Stok 2 unit ini "di-reserve" dan harus kembali saat pesanan dibatalkan.
        p.stock = 8
        db.session.commit()
        return {
            'admin_id': adm.id,
            'cust_id': cust.id,
            'product_id': p.id,
            'order_id': order.id,
        }


# ─── 1 & 2. _log() dengan user_id eksplisit tidak boleh 500 ───────────────────


def test_admin_create_produk_tidak_500():
    """Dulu `_log()` menerima user_id dua kali -> TypeError -> HTTP 500."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(
            '/admin/produk/baru',
            data={
                'name': 'Produk Baru',
                'category': 'kaos',
                'price': '25000',
                'stock': '3',
                'is_active': 'y',
            },
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        p = Product.query.filter_by(name='Produk Baru').first()
        assert p is not None
        assert p.stock == 3


def test_admin_edit_hapus_produk_tidak_500():
    """Edit & hapus produk juga memanggil _log() dengan user_id eksplisit."""
    app = _make_app()
    ids = _seed(app)
    pid = ids['product_id']

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(
            f'/admin/produk/{pid}/edit',
            data={
                'name': 'Kaos Reg Edit',
                'category': 'kaos',
                'price': '60000',
                'stock': '7',
                'is_active': 'y',
            },
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

        r = c.post(f'/admin/produk/{pid}/hapus')
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        assert db.session.get(Product, pid) is None


def test_admin_ubah_status_user_tidak_500():
    """Toggle status user juga lewat _log(user_id=...)."""
    app = _make_app()
    ids = _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(f"/admin/pengguna/{ids['cust_id']}/status")
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        u = db.session.get(User, ids['cust_id'])
        assert u.is_active is False


# ─── 3 & 4. Stok harus dikembalikan saat pesanan dibatalkan ──────────────────


def test_admin_batalkan_pesanan_kembalikan_stok():
    """Admin cancel pesanan dari menunggu_pembayaran harus mengembalikan stok."""
    app = _make_app()
    ids = _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(
            f"/admin/pesanan/{ids['order_id']}/status",
            data={'new_status': 'dibatalkan'},
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        p = db.session.get(Product, ids['product_id'])
        assert p.stock == 10, f'Stok harus kembali ke 10, dapat {p.stock}'
        order = db.session.get(Order, ids['order_id'])
        assert order.status == 'dibatalkan'


def test_customer_batalkan_pesanan_kembalikan_stok():
    """Customer cancel pesanan juga harus mengembalikan stok."""
    app = _make_app()
    ids = _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'cust@reg.test', 'password': 'Cust12345678'},
        )
        r = c.post(f"/pesanan/{ids['order_id']}/batalkan", follow_redirects=False)
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        p = db.session.get(Product, ids['product_id'])
        assert p.stock == 10, f'Stok harus kembali ke 10, dapat {p.stock}'


# ─── 5. Rate limit register ──────────────────────────────────────────────────


def test_rate_limit_register_menghasilkan_429():
    """Batas 5/jam untuk POST /auth/register harus benar-benar ditegakkan."""
    app = _make_app(ratelimit=True)

    with app.test_client() as c:
        statuses = []
        for i in range(7):
            r = c.post(
                '/auth/register',
                data={
                    'email': f'baru{i}@reg.test',
                    'password': 'Password12345',
                    'password2': 'Password12345',
                },
            )
            statuses.append(r.status_code)

    assert 429 in statuses, f'Harus ada 429, dapat {statuses}'


# ─── 6. Validasi form produk ─────────────────────────────────────────────────


def test_produk_tanpa_ukuran_tanpa_stok_ditolak():
    """Stok wajib diisi bila produk tidak memakai ukuran (dulu validator mati)."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(
            '/admin/produk/baru',
            data={
                'name': 'Tanpa Stok',
                'category': 'kaos',
                'price': '25000',
                'is_active': 'y',
            },
        )
        assert r.status_code == 200, f'Expected 200 (form error), got {r.status_code}'
        assert b'wajib diisi' in r.data

    with app.app_context():
        assert Product.query.filter_by(name='Tanpa Stok').first() is None


def test_produk_dengan_ukuran_tanpa_stok_tunggal_boleh():
    """Produk per-ukuran tidak wajib mengisi stok tunggal."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.post(
            '/admin/produk/baru',
            data={
                'name': 'Pakai Ukuran',
                'category': 'kaos',
                'price': '25000',
                'use_sizes': 'y',
                'stock_S': '2',
                'stock_M': '2',
                'stock_L': '2',
                'stock_XL': '2',
                'stock_XXL': '2',
                'is_active': 'y',
            },
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        p = Product.query.filter_by(name='Pakai Ukuran').first()
        assert p is not None
        assert p.use_sizes is True
        assert p.total_stock == 10


# ─── 7. sort=populer ─────────────────────────────────────────────────────────


def test_sort_populer_urutkan_berdasarkan_jumlah_ulasan():
    """`sort=populer` harus diimplementasikan (dulu hanya ada di whitelist)."""
    app = _make_app()
    ids = _seed(app)

    with app.app_context():
        _popular = Product(
            name='Produk Populer',
            description='',
            category='kaos',
            price=1000,
            is_active=True,
            use_sizes=False,
            stock=1,
        )
        db.session.add(_popular)
        db.session.flush()

        # Satu pengguna hanya boleh mengulas satu produk, jadi butuh 3 user
        # berbeda untuk 3 ulasan pada produk populer.
        reviewers = [
            User(
                email=f'rev{i}@reg.test',
                password_hash=hash_password('Rev12345678'),
                role='customer',
                is_active=True,
            )
            for i in range(3)
        ]
        db.session.add_all(reviewers)
        db.session.flush()

        for r in reviewers:
            db.session.add(
                Review(
                    product_id=_popular.id,
                    user_id=r.id,
                    rating=5,
                    comment='bagus',
                )
            )
        db.session.add(
            Review(
                product_id=ids['product_id'],
                user_id=ids['cust_id'],
                rating=3,
                comment='ok',
            )
        )
        db.session.commit()
        popular_id = _popular.id

    with app.test_client() as c:
        r = c.get('/katalog/?sort=populer')
        assert r.status_code == 200
        body = r.data.decode('utf-8', 'replace')
        assert body.index('Produk Populer') < body.index('Kaos Reg'), (
            'Produk dengan ulasan lebih banyak harus muncul lebih dulu'
        )

    with app.app_context():
        assert popular_id != ids['product_id']


# ─── 8. Login dengan next= ───────────────────────────────────────────────────


def test_login_honor_next():
    """Setelah login, user diarahkan ke URL `next` yang diminta."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.get('/admin/produk')
        r = c.post(
            '/auth/login?next=/admin/produk',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/admin/produk'), (
            f'Location: {r.headers["Location"]}'
        )


def test_login_next_menolak_open_redirect():
    """`next` ke domain lain harus diabaikan (tidak jadi open redirect)."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        r = c.post(
            '/auth/login?next=https://evil.example/steal',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        assert r.status_code == 302
        assert 'evil.example' not in r.headers['Location'], (
            f'Location: {r.headers["Location"]}'
        )


# ─── 9. Product.id autoincrement ─────────────────────────────────────────────


def test_product_id_berurutan_dan_unik():
    """Product.id harus AUTO_INCREMENT, bukan acak 31-bit."""
    app = _make_app()
    _seed(app)

    with app.app_context():
        ids = [Product(name=f'P{i}', category='kaos', price=1000) for i in range(5)]
        db.session.add_all(ids)
        db.session.commit()
        generated = [p.id for p in ids]

    assert len(set(generated)) == 5, 'ID produk harus unik'
    assert all(isinstance(i, int) and i > 0 for i in generated)
    assert max(generated) - min(generated) < 1000, (
        'ID produk seharusnya AUTO_INCREMENT (berurutan), bukan acak'
    )


# ─── 10. URL gambar produk di form admin ─────────────────────────────────────


def test_form_admin_gambar_pakai_route_media():
    """URL preview gambar harus ke /media/produk/..., bukan static/ (404)."""
    app = _make_app()
    ids = _seed(app)

    with app.app_context():
        p = db.session.get(Product, ids['product_id'])
        p.image = 'a' * 32 + '.jpg'
        db.session.commit()

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'adm@reg.test', 'password': 'Admin12345678'},
        )
        r = c.get(f"/admin/produk/{ids['product_id']}/edit")
        assert r.status_code == 200
        body = r.data.decode('utf-8', 'replace')
        assert '/media/produk/' in body, 'Gambar harus pakai route media'
        assert 'static/uploads' not in body, 'Jangan pakai static/ (folder tidak ada)'


# ─── 11. RATE_LIMIT_DEFAULT diteruskan ke Flask-Limiter ─────────────────────


def test_rate_limit_default_dikonfigurasi():
    """RATE_LIMIT_DEFAULT dari config harus masuk ke app.config Flask-Limiter."""
    app = _make_app()
    assert app.config.get('RATELIMIT_DEFAULT'), 'RATELIMIT_DEFAULT tidak terpasang'


# ─── Bonus: keranjang & upload bukti tetap berjalan setelah refactor ─────────


def test_keranjang_tambah_dan_update():
    """Alur keranjang inti masih berfungsi."""
    app = _make_app()
    ids = _seed(app)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'cust@reg.test', 'password': 'Cust12345678'},
        )
        r = c.post(
            '/keranjang/tambah',
            data={'product_id': str(ids['product_id']), 'quantity': '2'},
        )
        assert r.status_code in (200, 302), f'Got {r.status_code}'

    with app.app_context():
        item = CartItem.query.filter_by(user_id=ids['cust_id']).first()
        assert item is not None
        assert item.quantity == 2


def test_upload_bukti_berkas_valid():
    """Upload bukti bayar JPEG valid harus sukses."""
    from PIL import Image

    app = _make_app()
    ids = _seed(app)

    buf = io.BytesIO()
    Image.new('RGB', (1, 1), color=(255, 255, 255)).save(buf, format='JPEG')
    buf.seek(0)

    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'cust@reg.test', 'password': 'Cust12345678'},
        )
        r = c.post(
            f"/pesanan/{ids['order_id']}/upload-bukti",
            data={'bukti': (buf, 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        order = db.session.get(Order, ids['order_id'])
        assert order.status == 'menunggu_verifikasi'
        assert order.payment_proof is not None
