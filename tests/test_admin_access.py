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
            email='cust@merchku.test', password_hash=hash_password('Customer12345'),
            role='customer', is_active=True,
        )
        adm = User(
            email='adm@merchku.test', password_hash=hash_password('Admin12345678'),
            role='admin', is_active=True,
        )
        db.session.add_all([cust, adm])
        db.session.commit()
    return app


def test_customer_cannot_access_admin():
    app = _make_app()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'cust@merchku.test', 'password': 'Customer12345'})
        assert c.get('/admin/').status_code == 403
        assert c.get('/admin/produk').status_code == 403
        assert c.get('/admin/produk/baru').status_code == 403


def test_admin_can_access_admin_pages():
    app = _make_app()
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'adm@merchku.test', 'password': 'Admin12345678'})
        dashboard = c.get('/admin/')
        assert dashboard.status_code == 200
        assert b'Menunggu Verifikasi' in dashboard.data
        assert b'Pesanan Terbaru' in dashboard.data
        assert c.get('/admin/produk').status_code == 200
        assert c.get('/admin/produk/baru').status_code == 200
