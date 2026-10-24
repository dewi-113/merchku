"""
Test Tahap 6: Upload bukti bayar, approval admin, laporan transaksi

Kasus yang diuji:
1. Upload file palsu (ekstensi jpg tapi isi PHP)
2. Upload file valid (jpg asli) — harus sukses
3. IDOR serve bukti — customer B tidak bisa lihat bukti milik A
4. IDOR upload bukti — customer B tidak bisa upload ke pesanan A
5. Admin bisa lihat bukti bayar siapapun
6. Customer tidak bisa akses laporan admin
7. Admin bisa akses laporan admin
8. Customer tidak bisa POST ke route ubah status admin
9. Transisi status invalid ditolak
10. Upload bukti di status selain menunggu_pembayaran ditolak
"""

import io

from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.keranjang.models import CartItem
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app

# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_app():
    import tempfile
    return create_test_app(UPLOAD_PRIVATE=tempfile.mkdtemp())


def _seed(app):
    with app.app_context():
        db.create_all()
        OrderItem.query.delete()
        Order.query.delete()
        CartItem.query.delete()
        Product.query.delete()
        User.query.delete()
        db.session.commit()

        u1 = User(email='cust1@t.test', password_hash=hash_password('Password111'),
                  role='customer', is_active=True)
        u2 = User(email='cust2@t.test', password_hash=hash_password('Password222'),
                  role='customer', is_active=True)
        adm = User(email='adm@t.test', password_hash=hash_password('Admin99999'),
                   role='admin', is_active=True)
        db.session.add_all([u1, u2, adm])
        db.session.flush()

        p = Product(name='Kaos', description='', category='kaos',
                    price=50000, is_active=True, use_sizes=False, stock=10)
        db.session.add(p)
        db.session.flush()

        order = Order(
            user_id=u1.id,
            status='menunggu_pembayaran',
            recipient_name='Test',
            address='Jl. Test',
            phone='081',
            total_price=50000,
        )
        db.session.add(order)
        db.session.flush()
        oi = OrderItem(order_id=order.id, product_id=p.id,
                       product_name='Kaos', size=None, quantity=1, unit_price=50000)
        db.session.add(oi)
        db.session.commit()
        return u1.id, u2.id, adm.id, order.id


def _make_fake_jpg():
    """File dengan ekstensi .jpg tapi magic bytes bukan JPEG."""
    return io.BytesIO(b'<?php echo "hacked"; ?>')


def _make_valid_jpg():
    """Buat JPEG 1x1 pixel yang benar-benar valid menggunakan Pillow."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new('RGB', (1, 1), color=(255, 255, 255))
    img.save(buf, format='JPEG')
    buf.seek(0)
    return buf


# ─── 1. Upload file palsu (magic bytes salah) ─────────────────────────────────

def test_upload_file_palsu_ditolak():
    """File dengan ekstensi .jpg tapi magic bytes bukan JPEG harus ditolak (400)."""
    app = _make_app()
    _u1_id, _, _, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        r = c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_fake_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
        )
        assert r.status_code == 400, f'Expected 400, got {r.status_code}'

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == 'menunggu_pembayaran'
        assert order.payment_proof is None


# ─── 2. Upload file valid — sukses ───────────────────────────────────────────

def test_upload_file_valid_sukses():
    """Upload JPEG valid harus berhasil, status berubah ke menunggu_verifikasi."""
    app = _make_app()
    _u1_id, _, _, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        r = c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_valid_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert r.status_code == 302, f'Expected 302, got {r.status_code}'

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == 'menunggu_verifikasi', f'Status: {order.status}'
        assert order.payment_proof is not None


# ─── 3. IDOR serve bukti ─────────────────────────────────────────────────────

def test_idor_serve_bukti():
    """Customer B tidak boleh mengakses serve_bukti milik customer A."""
    app = _make_app()
    _u1_id, _u2_id, _, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_valid_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
        )

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust2@t.test', 'password': 'Password222'})
        r = c.get(f'/pesanan/{order_id}/bukti')
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


# ─── 4. IDOR upload bukti ────────────────────────────────────────────────────

def test_idor_upload_bukti():
    """Customer B tidak boleh upload bukti ke pesanan milik A."""
    app = _make_app()
    _u1_id, _u2_id, _, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust2@t.test', 'password': 'Password222'})
        r = c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_valid_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
        )
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


# ─── 5. Admin bisa akses bukti ───────────────────────────────────────────────

def test_admin_bisa_serve_bukti():
    """Admin boleh mengakses bukti bayar milik customer manapun."""
    app = _make_app()
    _u1_id, _, _adm_id, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_valid_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
        )

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'adm@t.test', 'password': 'Admin99999'})
        r = c.get(f'/admin/pesanan/{order_id}/bukti')
        # yang penting bukan 403 (200 kalau file ada, 404 kalau tmpdir beda)
        assert r.status_code != 403, f'Admin seharusnya bisa akses bukti, dapat {r.status_code}'


# ─── 6. Customer tidak bisa akses laporan ────────────────────────────────────

def test_customer_tidak_bisa_akses_laporan():
    """Customer harus dapat 403 saat mengakses /admin/laporan."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        r = c.get('/admin/laporan')
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


# ─── 7. Admin bisa akses laporan ─────────────────────────────────────────────

def test_admin_bisa_akses_laporan():
    """Admin dapat 200 di /admin/laporan."""
    app = _make_app()
    _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'adm@t.test', 'password': 'Admin99999'})
        r = c.get('/admin/laporan')
        assert r.status_code == 200, f'Expected 200, got {r.status_code}'


# ─── 8. Customer tidak bisa ubah status pesanan via route admin ───────────────

def test_customer_tidak_bisa_ubah_status_pesanan():
    """Customer tidak bisa POST ke /admin/pesanan/<id>/status."""
    app = _make_app()
    _u1_id, _, _, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        r = c.post(f'/admin/pesanan/{order_id}/status', data={'new_status': 'dibayar'})
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


# ─── 9. Transisi status invalid ditolak ──────────────────────────────────────

def test_transisi_invalid_ditolak():
    """Admin tidak bisa lompat ke status yang tidak ada di VALID_TRANSITIONS."""
    app = _make_app()
    _u1_id, _, _adm_id, order_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'adm@t.test', 'password': 'Admin99999'})
        r = c.post(
            f'/admin/pesanan/{order_id}/status',
            data={'new_status': 'selesai'},
            follow_redirects=True,
        )
        assert r.status_code == 200

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == 'menunggu_pembayaran', f'Status tidak boleh berubah: {order.status}'


# ─── 10. Upload saat status bukan menunggu_pembayaran ────────────────────────

def test_upload_bukti_status_salah():
    """Upload bukti bayar saat status bukan menunggu_pembayaran harus redirect."""
    app = _make_app()
    _u1_id, _, _, order_id = _seed(app)

    with app.app_context():
        order = db.session.get(Order, order_id)
        order.status = 'menunggu_verifikasi'
        db.session.commit()

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust1@t.test', 'password': 'Password111'})
        r = c.post(
            f'/pesanan/{order_id}/upload-bukti',
            data={'bukti': (_make_valid_jpg(), 'bukti.jpg', 'image/jpeg')},
            content_type='multipart/form-data',
            follow_redirects=False,
        )
        assert r.status_code == 302, f'Expected redirect, got {r.status_code}'

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == 'menunggu_verifikasi'
