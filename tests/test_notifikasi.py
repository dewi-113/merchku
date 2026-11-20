from app import db
from app.notifikasi.models import Notification
from app.pesanan.models import Order
from tests.test_seller_verifikasi import _login, _setup


def _notif(app, email):
    from app.auth.models import User
    with app.app_context():
        uid = User.query.filter_by(email=email).one().id
        return [n.message for n in Notification.query.filter_by(user_id=uid).order_by(Notification.id)]


def test_pembeli_dapat_notifikasi_saat_penjual_konfirmasi_dan_kirim():
    app, oid = _setup()
    with app.test_client() as c:
        _login(c)
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibayar'})
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dikirim', 'tracking_number': 'JNE123456'})
    msgs = _notif(app, 'b@t.test')
    assert any('dikonfirmasi' in m for m in msgs)
    assert any('JNE123456' in m for m in msgs)


def test_penjual_dapat_notifikasi_saat_pembeli_terima_dan_lonceng_tampil():
    app, oid = _setup()
    with app.app_context():
        db.session.get(Order, oid).status = 'dikirim'
        db.session.commit()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Customer12345'})
        c.post(f'/pesanan/{oid}/diterima')
    assert any('diterima pembeli' in m for m in _notif(app, 's1@t.test'))
    with app.test_client() as c:
        _login(c)
        home = c.get('/').get_data(as_text=True)
        assert 'nav-bell' in home and '1 belum dibaca' in home
        page = c.get('/notifikasi/').get_data(as_text=True)
        assert 'diterima pembeli' in page
        assert '1 belum dibaca' not in c.get('/').get_data(as_text=True)


def test_notifikasi_orang_lain_tidak_bisa_dibuka():
    app, oid = _setup()
    with app.test_client() as c:
        _login(c)
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibayar'})
    with app.app_context():
        nid = Notification.query.first().id
    with app.test_client() as c:
        _login(c)  # penjual, bukan pemilik notifikasi pembeli
        assert c.get(f'/notifikasi/{nid}/buka').status_code == 404


def test_nota_pembeli_dan_penjual():
    app, oid = _setup(second_shop_item=True)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Customer12345'})
        r = c.get(f'/pesanan/{oid}/nota')
        assert r.status_code == 200
        page = r.get_data(as_text=True)
        assert 'NOTA PESANAN' in page and 'Stiker' in page and 'Topi' in page
    with app.test_client() as c:
        _login(c)  # penjual s1: hanya produk tokonya
        page = c.get(f'/seller/pesanan/{oid}/nota').get_data(as_text=True)
        assert 'Stiker' in page and 'Topi' not in page and 'Total toko' in page
        assert c.get(f'/pesanan/{oid}/nota').status_code == 403  # bukan pemilik pesanan


def test_halaman_log_keamanan_admin():
    from app.auth.models import User
    from app.auth.security import hash_password
    app, _ = _setup()
    with app.app_context():
        db.session.add(User(email='adm@t.test', password_hash=hash_password('Admin123456'), role='admin', is_active=True))
        db.session.commit()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'salah-password'})  # memicu login_failed
        assert c.get('/admin/log-keamanan').status_code in (302, 401, 403)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'adm@t.test', 'password': 'Admin123456'})
        r = c.get('/admin/log-keamanan')
        assert r.status_code == 200
        page = r.get_data(as_text=True)
        assert 'Log Keamanan' in page and 'Login gagal' in page
        assert c.get('/admin/log-keamanan?event=login_failed&q=b@t.test').status_code == 200
