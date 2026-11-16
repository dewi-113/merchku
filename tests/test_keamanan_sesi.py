"""Keamanan sesi: akun nonaktif, ganti password, cache, logout, stok saat batal."""
from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.keranjang.models import CartItem
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app

PW = 'Password12345'


def _make_app(**overrides):
    app = create_test_app(**overrides)
    with app.app_context():
        cust = User(email='cust@merchku.test', password_hash=hash_password(PW), role='customer', is_active=True)
        adm = User(email='adm@merchku.test', password_hash=hash_password(PW), role='admin', is_active=True)
        db.session.add_all([cust, adm])
        db.session.commit()
        app.ids = {'cust': cust.id, 'adm': adm.id}
    return app


def _login(c, email='cust@merchku.test', pw=PW):
    return c.post('/auth/login', data={'email': email, 'password': pw})


def test_akun_dinonaktifkan_langsung_keluar_dari_sesi():
    app = _make_app()
    with app.test_client() as c:
        _login(c)
        assert c.get('/profil/').status_code == 200
        with app.app_context():
            db.session.get(User, app.ids['cust']).is_active = False
            db.session.commit()
        assert c.get('/profil/').status_code == 302


def test_ganti_password_mengeluarkan_sesi_di_perangkat_lain():
    app = _make_app()
    lain = app.test_client()
    ini = app.test_client()
    _login(lain)
    _login(ini)
    resp = ini.post('/profil/ganti-password', data={
        'pw-password_lama': PW,
        'pw-password_baru': 'PasswordBaru123',
        'pw-password_baru2': 'PasswordBaru123',
    })
    assert resp.status_code == 302
    # perangkat yang mengganti password tetap login
    assert ini.get('/profil/').status_code == 200
    # perangkat lain harus login ulang
    assert lain.get('/profil/').status_code == 302


def test_halaman_pribadi_tidak_dicache():
    app = _make_app()
    with app.test_client() as c:
        _login(c)
        resp = c.get('/profil/')
        assert 'no-store' in resp.headers.get('Cache-Control', '')


def test_logout_tanpa_token_tidak_mengeluarkan_pengguna():
    app = _make_app(WTF_CSRF_ENABLED=True)
    with app.test_client() as c:
        # login lewat sesi langsung karena form login butuh token CSRF
        with c.session_transaction() as s:
            with app.app_context():
                s['_user_id'] = db.session.get(User, app.ids['cust']).get_id()
            s['_fresh'] = True
        assert c.get('/profil/').status_code == 200
        c.get('/auth/logout')  # mis. dipicu <img src> dari situs lain
        assert c.get('/profil/').status_code == 200


def test_password_terlalu_panjang_ditolak():
    app = _make_app()
    with app.test_client() as c:
        resp = c.post('/auth/register', data={
            'email': 'baru@merchku.test', 'password': 'a' * 200, 'password2': 'a' * 200, 'role': 'customer',
        })
        assert resp.status_code == 200
        with app.app_context():
            assert User.query.filter_by(email='baru@merchku.test').first() is None


def test_admin_batalkan_lewat_panel_seller_mengembalikan_stok():
    app = _make_app()
    with app.app_context():
        p = Product(name='Kaos', category='kaos', price=50000, stock=3, is_active=True)
        db.session.add(p)
        db.session.flush()
        o = Order(user_id=app.ids['cust'], recipient_name='Budi', address='Jl. A', phone='0812',
                  total_price=100000, status='menunggu_pembayaran')
        o.items.append(OrderItem(product_id=p.id, product_name='Kaos', quantity=2, unit_price=50000))
        db.session.add(o)
        db.session.commit()
        pid, oid = p.id, o.id
    with app.test_client() as c:
        _login(c, 'adm@merchku.test')
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibatalkan'})
    with app.app_context():
        assert db.session.get(Order, oid).status == 'dibatalkan'
        assert db.session.get(Product, pid).stock == 5


def test_total_keranjang_tidak_menghitung_produk_nonaktif():
    app = _make_app()
    with app.app_context():
        aktif = Product(name='Aktif', category='kaos', price=10000, stock=5, is_active=True)
        mati = Product(name='Mati', category='kaos', price=99000, stock=5, is_active=False)
        db.session.add_all([aktif, mati])
        db.session.flush()
        db.session.add_all([
            CartItem(user_id=app.ids['cust'], product_id=aktif.id, quantity=1),
            CartItem(user_id=app.ids['cust'], product_id=mati.id, quantity=1),
        ])
        db.session.commit()
    with app.test_client() as c:
        _login(c)
        html = c.get('/keranjang/').data.decode()
        assert '99.000' not in html.split('Total')[-1][:300]
