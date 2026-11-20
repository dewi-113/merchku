from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app


def _setup(second_shop_item=False):
    app = create_test_app()
    with app.app_context():
        buyer = User(email='b@t.test', password_hash=hash_password('Customer12345'), role='customer', is_active=True)
        s1 = User(email='s1@t.test', password_hash=hash_password('Seller123456'), role='seller', is_active=True)
        s2 = User(email='s2@t.test', password_hash=hash_password('Seller123456'), role='seller', is_active=True)
        db.session.add_all([buyer, s1, s2])
        db.session.flush()
        p1 = Product(name='Stiker', price=18000, owner_id=s1.id, stock=10)
        p2 = Product(name='Topi', price=50000, owner_id=s2.id, stock=10)
        db.session.add_all([p1, p2])
        db.session.flush()
        order = Order(user_id=buyer.id, status='menunggu_verifikasi', recipient_name='rene',
                      address='polibatam', phone='0812', payment_proof='bukti.png', total_price=18000)
        db.session.add(order)
        db.session.flush()
        db.session.add(OrderItem(order_id=order.id, product_id=p1.id, product_name='Stiker',
                                 quantity=1, unit_price=18000))
        if second_shop_item:
            db.session.add(OrderItem(order_id=order.id, product_id=p2.id, product_name='Topi',
                                     quantity=1, unit_price=50000))
        db.session.commit()
        oid = order.id
    return app, oid


def _login(c):
    c.post('/auth/login', data={'email': 's1@t.test', 'password': 'Seller123456'})


def test_seller_bisa_konfirmasi_pembayaran_pesanan_tokonya():
    app, oid = _setup()
    with app.test_client() as c:
        _login(c)
        assert b'Konfirmasi Pembayaran' in c.get(f'/seller/pesanan/{oid}').data
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibayar'})
    with app.app_context():
        assert db.session.get(Order, oid).status == 'dibayar'


def test_seller_bisa_tolak_bukti_bayar():
    app, oid = _setup()
    with app.test_client() as c:
        _login(c)
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'ditolak'})
    with app.app_context():
        assert db.session.get(Order, oid).status == 'ditolak'


def test_pesanan_multi_toko_tetap_diverifikasi_admin():
    app, oid = _setup(second_shop_item=True)
    with app.test_client() as c:
        _login(c)
        assert b'Konfirmasi Pembayaran' not in c.get(f'/seller/pesanan/{oid}').data
        assert c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibayar'}).status_code == 403
    with app.app_context():
        assert db.session.get(Order, oid).status == 'menunggu_verifikasi'


def test_dashboard_tampilkan_performa_toko():
    app, oid = _setup()
    with app.test_client() as c:
        _login(c)
        c.post(f'/seller/pesanan/{oid}/status', data={'new_status': 'dibayar'})
        r = c.get('/seller/')
        assert r.status_code == 200
        assert b'Performa Toko' in r.data
        assert b'Rp 18.000' in r.data
        assert b'Stiker' in r.data


def test_cli_bersihkan_dan_reset_demo():
    app, _ = _setup()
    with app.app_context():
        s1 = User.query.filter_by(email='s1@t.test').one()
        s1.shop_name = '{{7*7}}sst'
        db.session.add(Product(name='{{7*7}}', price=1000, owner_id=s1.id, stock=1))
        db.session.add(User(email='seller@demo.test', password_hash='x', role='seller',
                            is_active=True, failed_attempts=5))
        db.session.commit()
    runner = app.test_cli_runner()
    assert runner.invoke(args=['bersihkan-nama-toko', '--terapkan']).exit_code == 0
    assert runner.invoke(args=['reset-akun-demo']).exit_code == 0
    with app.app_context():
        assert User.query.filter_by(email='s1@t.test').one().shop_name is None
        assert Product.query.filter_by(name='{{7*7}}').one().is_active is False
        assert User.query.filter_by(email='seller@demo.test').one().failed_attempts == 0
    with app.test_client() as c:
        r = c.post('/auth/login', data={'email': 'seller@demo.test', 'password': 'SellerDemo1234'})
        assert r.status_code == 302
