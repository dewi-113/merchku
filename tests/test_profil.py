import io

from app import db
from app.auth.models import User
from app.auth.security import hash_password, verify_password
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    app.config['METRICS_TOKEN'] = 'test-token-rahasia'
    import tempfile
    app.config['UPLOAD_PUBLIC'] = tempfile.mkdtemp()
    return app


def _seed(app):
    with app.app_context():
        db.create_all()
        User.query.delete()
        db.session.commit()
        u = User(email='user@t.test', password_hash=hash_password('Password111'),
                 role='customer', is_active=True)
        db.session.add(u)
        db.session.commit()
        return u.id


def _valid_jpg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), (200, 100, 50)).save(buf, format='JPEG')
    buf.seek(0)
    return buf


def _fake_jpg():
    return io.BytesIO(b'<?php system(chr(99)); ?>')


def test_profil_butuh_login():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        r = c.get('/profil/', follow_redirects=False)
        assert r.status_code in (302, 401)


def test_profil_200_setelah_login():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        home = c.get('/')
        assert b"href='/profil/' aria-label='Buka profil saya'" in home.data
        assert b"class='btn-nav-logout' href='/auth/logout?token=" in home.data
        r = c.get('/profil/')
        assert r.status_code == 200
        assert b'profile-account-banner' in r.data
        assert b'Keamanan Akun' in r.data
        assert b'Alamat Pengiriman' in r.data
        assert b'password_lama' not in r.data
        assert b'Profil &amp; alamat' in r.data
        security = c.get('/profil/keamanan')
        assert security.status_code == 200
        assert security.headers['Cache-Control'] == 'no-store'
        assert b'password_lama' in security.data


def test_halaman_keamanan_butuh_login():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        response = c.get('/profil/keamanan', follow_redirects=False)
        assert response.status_code in (302, 401)


def test_pembeli_tidak_bisa_mengubah_role_menjadi_penjual():
    app = _make_app()
    uid = _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        profile = c.get('/profil/')
        assert b'Buka Toko' not in profile.data
        response = c.post('/profil/buka-toko', follow_redirects=True)
        assert response.status_code == 200
        assert b'tidak dapat diubah menjadi akun penjual' in response.data.lower()
    with app.app_context():
        assert db.session.get(User, uid).role == 'customer'


def test_pembeli_bisa_menyimpan_alamat_dari_profil():
    app = _make_app()
    uid = _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        response = c.post('/profil/alamat', data={
            'addr-recipient_name': 'Dewi Pembeli',
            'addr-phone': '+628123456789',
            'addr-address': 'Jl. Melati No. 12, RT 02/RW 01',
            'addr-address_label': 'rumah',
            'addr-district': 'Coblong',
            'addr-city': 'Bandung',
            'addr-province': 'Jawa Barat',
            'addr-postal_code': '40123',
            'addr-delivery_note': 'Rumah pagar putih',
        })
        assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, uid)
        assert user.has_shipping_details
        assert user.recipient_name == 'Dewi Pembeli'
        assert user.address == 'Jl. Melati No. 12, RT 02/RW 01'
        assert user.phone == '+628123456789'
        assert user.delivery_note == 'Rumah pagar putih'


def test_ganti_password_berhasil():
    app = _make_app()
    uid = _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        r = c.post('/profil/ganti-password', data={
            'pw-password_lama': 'Password111',
            'pw-password_baru': 'NewPassword999',
            'pw-password_baru2': 'NewPassword999',
        }, follow_redirects=False)
        assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, uid)
        assert verify_password(u.password_hash, 'NewPassword999')
        assert not verify_password(u.password_hash, 'Password111')


def test_ganti_password_gagal_lama_salah():
    app = _make_app()
    uid = _seed(app)
    with app.app_context():
        h = db.session.get(User, uid).password_hash
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        c.post('/profil/ganti-password', data={
            'pw-password_lama': 'SalahTotal!!',
            'pw-password_baru': 'NewPassword999',
            'pw-password_baru2': 'NewPassword999',
        })
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.password_hash == h


def test_upload_avatar_palsu_ditolak():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        r = c.post('/profil/upload-avatar',
                   data={'av-avatar': (_fake_jpg(), 'foto.jpg', 'image/jpeg')},
                   content_type='multipart/form-data')
        assert r.status_code == 400
    with app.app_context():
        u = User.query.filter_by(email='user@t.test').first()
        assert u.avatar is None


def test_upload_avatar_valid_berhasil():
    app = _make_app()
    uid = _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'user@t.test', 'password': 'Password111'})
        r = c.post('/profil/upload-avatar',
                   data={'av-avatar': (_valid_jpg(), 'foto.jpg', 'image/jpeg')},
                   content_type='multipart/form-data',
                   follow_redirects=False)
        assert r.status_code == 302
    with app.app_context():
        u = db.session.get(User, uid)
        assert u.avatar is not None
        assert u.avatar.endswith('.jpg')


def test_metrics_tanpa_token():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        r = c.get('/metrics')
        assert r.status_code == 403


def test_metrics_token_salah():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        r = c.get('/metrics?token=salah')
        assert r.status_code == 403


def test_metrics_token_benar():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        r = c.get('/metrics?token=test-token-rahasia')
        assert r.status_code == 200
        body = r.data.decode()
        assert 'merchku_users_total' in body
        assert 'merchku_products_total' in body
        assert 'merchku_orders_by_status' in body


def test_landing_page_publik():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        r = c.get('/')
        assert r.status_code == 200
        assert b'Merchku' in r.data
        assert b'Promo Merchku' in r.data
