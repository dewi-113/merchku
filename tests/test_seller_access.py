from app import db
from app.auth.models import User
from app.auth.security import hash_password
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()
        cust = User(
            email='buyer@merchku.test', password_hash=hash_password('Customer12345'),
            role='customer', is_active=True,
        )
        seller = User(
            email='seller@merchku.test', password_hash=hash_password('Seller123456'),
            role='seller', is_active=True,
        )
        db.session.add_all([cust, seller])
        db.session.commit()
    return app


def test_customer_cannot_change_to_seller():
    app = _make_app()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'buyer@merchku.test', 'password': 'Customer12345'})
        assert b'Buka Toko' not in c.get('/').data
        assert b'Buka Toko' not in c.get('/profil/').data
        r = c.post('/profil/buka-toko', follow_redirects=True)
        assert r.status_code == 200
        assert b'tidak dapat diubah menjadi akun penjual' in r.data.lower()
        with app.app_context():
            assert User.query.filter_by(email='buyer@merchku.test').one().role == 'customer'
        assert c.get('/seller/').status_code == 403
        assert c.get('/seller/produk/baru').status_code == 403


def test_seller_can_manage_store():
    app = _make_app()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'seller@merchku.test', 'password': 'Seller123456'})
        assert c.get('/seller/').status_code == 200
        assert c.get('/seller/produk').status_code == 200
        assert c.get('/seller/produk/baru').status_code == 200
        assert c.get('/seller/pesanan').status_code == 200
        assert c.get('/seller/toko').status_code == 200


def test_customer_cannot_access_seller_area():
    app = _make_app()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'buyer@merchku.test', 'password': 'Customer12345'})
        assert c.get('/seller/').status_code == 403
        assert c.get('/seller/produk').status_code == 403
