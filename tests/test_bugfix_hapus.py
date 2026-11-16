"""Regresi: hapus produk/pengguna yang sudah punya riwayat pesanan, login akun nonaktif."""
from datetime import timedelta

from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app

PW = 'Password12345'


def _make_app():
    app = create_test_app()
    with app.app_context():
        adm = User(email='adm@merchku.test', password_hash=hash_password(PW), role='admin', is_active=True)
        cust = User(email='cust@merchku.test', password_hash=hash_password(PW), role='customer', is_active=True)
        seller = User(email='seller@merchku.test', password_hash=hash_password(PW), role='seller', is_active=True)
        db.session.add_all([adm, cust, seller])
        db.session.flush()
        p = Product(name='Kaos', category='kaos', price=50000, stock=5, owner_id=seller.id, is_active=True)
        db.session.add(p)
        db.session.flush()
        o = Order(user_id=cust.id, recipient_name='Budi', address='Jl. A', phone='0812',
                  total_price=50000, status='selesai')
        o.items.append(OrderItem(product_id=p.id, product_name='Kaos', quantity=1, unit_price=50000))
        db.session.add(o)
        db.session.commit()
        app.ids = {'adm': adm.id, 'cust': cust.id, 'seller': seller.id, 'product': p.id, 'order': o.id}
    return app


def _login(c, email):
    return c.post('/auth/login', data={'email': email, 'password': PW})


def test_admin_hapus_produk_yang_sudah_dipesan_diarsipkan():
    app = _make_app()
    pid, oid = app.ids['product'], app.ids['order']
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        resp = c.post(f'/admin/produk/{pid}/hapus')
        assert resp.status_code == 302
        with app.app_context():
            p = db.session.get(Product, pid)
            assert p is not None and p.is_active is False
        assert c.get(f'/admin/pesanan/{oid}').status_code == 200


def test_seller_hapus_produk_yang_sudah_dipesan_diarsipkan():
    app = _make_app()
    pid = app.ids['product']
    with app.test_client() as c:
        _login(c, 'seller@merchku.test')
        assert c.post(f'/seller/produk/{pid}/hapus').status_code == 302
        with app.app_context():
            p = db.session.get(Product, pid)
            assert p is not None and p.is_active is False


def test_admin_hapus_produk_tanpa_pesanan_benar_benar_terhapus():
    app = _make_app()
    with app.app_context():
        p = Product(name='Stiker', category='aksesoris', price=5000, stock=1, is_active=True)
        db.session.add(p)
        db.session.commit()
        pid = p.id
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        c.post(f'/admin/produk/{pid}/hapus')
        with app.app_context():
            assert db.session.get(Product, pid) is None


def test_admin_hapus_pengguna_yang_punya_riwayat_ditolak():
    app = _make_app()
    cid = app.ids['cust']
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        resp = c.post(f'/admin/pengguna/{cid}/hapus')
        assert resp.status_code == 302
        with app.app_context():
            assert db.session.get(User, cid) is not None
            assert db.session.get(Order, app.ids['order']) is not None


def test_admin_hapus_pengguna_tanpa_riwayat_berhasil():
    app = _make_app()
    with app.app_context():
        u = User(email='baru@merchku.test', password_hash=hash_password(PW), role='customer', is_active=True)
        db.session.add(u)
        db.session.commit()
        uid = u.id
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        c.post(f'/admin/pengguna/{uid}/hapus')
        with app.app_context():
            assert db.session.get(User, uid) is None


def test_login_akun_nonaktif_ditolak():
    app = _make_app()
    with app.app_context():
        u = db.session.get(User, app.ids['cust'])
        u.is_active = False
        db.session.commit()
    with app.test_client() as c:
        resp = _login(c, 'cust@merchku.test')
        assert resp.status_code == 200
        assert b'dinonaktifkan' in resp.data
        assert c.get('/keranjang/', follow_redirects=False).status_code == 302


def test_salah_password_setelah_kunci_habis_tidak_langsung_terkunci_lagi():
    app = _make_app()
    from app.auth.routes import _utcnow
    with app.app_context():
        u = db.session.get(User, app.ids['cust'])
        u.failed_attempts = 5
        u.locked_until = _utcnow() - timedelta(minutes=1)
        db.session.commit()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust@merchku.test', 'password': 'salah-salah-salah'})
        with app.app_context():
            u = db.session.get(User, app.ids['cust'])
            assert u.failed_attempts == 1
            assert u.locked_until is None or u.locked_until < _utcnow()


def test_gagal_kembalikan_stok_tidak_crash(monkeypatch):
    app = _make_app()
    with app.app_context():
        o = db.session.get(Order, app.ids['order'])
        o.status = 'menunggu_pembayaran'
        db.session.commit()

    def boom(order):
        raise RuntimeError('db down')

    monkeypatch.setattr('app.admin.routes.restore_reserved_stock', boom)
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        resp = c.post(f'/admin/pesanan/{app.ids["order"]}/status', data={'new_status': 'dibatalkan'})
        assert resp.status_code == 302
