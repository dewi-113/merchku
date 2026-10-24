import hashlib

from app import config_map, create_app, db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.keranjang.models import CartItem
from app.pesanan.models import Order
from config import DevConfig


def make_checkout_app():
    class CheckoutTestConfig(DevConfig):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        SECRET_KEY = 'checkout-test'
        SQLALCHEMY_DATABASE_URI = 'sqlite://'
        RATE_LIMIT_DEFAULT = None

    config_map['checkout_test'] = CheckoutTestConfig
    app = create_app('checkout_test')
    with app.app_context():
        db.create_all()
    return app


def seed_checkout_data(app):
    with app.app_context():
        user = User(
            email='buyer@example.test',
            password_hash=hash_password('Password111'),
            role='customer',
            is_active=True,
            recipient_name='Test Buyer',
            address='Jl Test',
            district='Coblong',
            city='Bandung',
            postal_code='40123',
            province='Jawa Barat',
            phone='08123456789',
        )
        product = Product(
            name='Kaos',
            description='',
            category='kaos',
            price=75000,
            is_active=True,
            use_sizes=False,
            stock=5,
        )
        db.session.add_all([user, product])
        db.session.commit()
        return user.id, product.id


def test_checkout_uses_live_biteship_rate_and_starts_midtrans(monkeypatch):
    import app.pesanan.routes as routes

    app = make_checkout_app()
    user_id, product_id = seed_checkout_data(app)
    rate = {
        'key': 'jne|reg',
        'courier': 'jne',
        'service': 'REG',
        'price': 15000,
        'duration': '2-3 days',
    }
    monkeypatch.setattr(routes, 'biteship_rates', lambda *_args: [rate])
    monkeypatch.setattr(
        routes,
        'create_midtrans_payment',
        lambda *_args: ('MERCHKU-1-test', 'snap-token', 'https://pay.example.test/snap'),
    )
    app.config.update(
        BITESHIP_API_KEY='test-key',
        SHIPPING_ORIGIN_POSTAL_CODE='40123',
        MIDTRANS_SERVER_KEY='test-server-key',
    )
    with app.app_context():
        db.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=2))
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'buyer@example.test', 'password': 'Password111'})
        checkout = client.get('/pesanan/checkout')
        assert checkout.status_code == 200
        assert b'Biteship' in checkout.data
        response = client.post('/pesanan/checkout', data={
            'courier': 'jne|reg',
            'payment_method': 'midtrans',
        })
        assert response.status_code == 302, response.data.decode().split('Not a valid choice')[0][-1000:]
        assert response.location.endswith('/pesanan/1/bayar')
        payment_response = client.get(response.location)
        assert payment_response.status_code == 302
        assert payment_response.location == 'https://pay.example.test/snap'

    with app.app_context():
        order = Order.query.one()
        assert order.total_price == 165000
        assert order.shipping_cost == 15000
        assert order.courier == 'jne'
        assert order.shipping_service == 'REG'
        assert order.payment_transaction_id == 'MERCHKU-1-test'
        assert order.payment_token == 'snap-token'


def test_checkout_calculates_fee_discount_and_fragile_protection_from_server(monkeypatch):
    import app.pesanan.routes as routes

    app = make_checkout_app()
    user_id, product_id = seed_checkout_data(app)
    rate = {
        'key': 'jne|reg',
        'courier': 'jne',
        'service': 'REG',
        'price': 15000,
        'duration': '2-3 days',
    }
    monkeypatch.setattr(routes, 'biteship_rates', lambda *_args: [rate])
    app.config.update(
        BITESHIP_API_KEY='test-key',
        SHIPPING_ORIGIN_POSTAL_CODE='40123',
        CHECKOUT_SERVICE_FEE_RP=1500,
        CHECKOUT_SHIPPING_DISCOUNT_RP=500,
        FRAGILE_PACKING_FEE_RP=2000,
    )
    with app.app_context():
        product = db.session.get(Product, product_id)
        product.is_fragile = True
        db.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=2))
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={
            'email': 'buyer@example.test',
            'password': 'Password111',
        })
        checkout = client.get('/pesanan/checkout')
        assert checkout.status_code == 200
        assert b'Perlindungan kemasan barang rawan pecah' in checkout.data
        assert b'Subtotal pesanan' in checkout.data
        assert b'Subtotal pengiriman' in checkout.data
        assert b'Diskon pengiriman' in checkout.data
        response = client.post('/pesanan/checkout', data={
            'courier': 'jne|reg',
            'payment_method': 'bank_transfer',
            'fragile_protection': 'y',
        })
        assert response.status_code == 302

    with app.app_context():
        order = Order.query.one()
        assert order.total_products == 150000
        assert order.shipping_cost == 15000
        assert order.shipping_discount == 500
        assert order.service_fee == 1500
        assert order.fragile_protection is True
        assert order.fragile_fee == 2000
        assert order.shipping_duration == '2-3 days'
        assert order.total_price == 168000
        item = order.items[0]
        assert item.product_description == ''


def test_midtrans_is_hidden_when_shipping_cannot_be_added_to_total():
    app = make_checkout_app()
    user_id, product_id = seed_checkout_data(app)
    app.config['MIDTRANS_SERVER_KEY'] = 'test-server-key'
    with app.app_context():
        db.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=1))
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'buyer@example.test', 'password': 'Password111'})
        response = client.get('/pesanan/checkout')
        assert response.status_code == 200
        assert b'value="midtrans"' not in response.data
        assert b'Biteship belum diatur' in response.data


def test_midtrans_webhook_checks_signature_and_marks_paid():
    app = make_checkout_app()
    user_id, _product_id = seed_checkout_data(app)
    app.config['MIDTRANS_SERVER_KEY'] = 'server-key'
    with app.app_context():
        order = Order(
            user_id=user_id,
            status='menunggu_pembayaran',
            recipient_name='Test Buyer',
            address='Jl Test',
            phone='08123456789',
            total_price=75000,
            payment_method='midtrans',
            payment_transaction_id='MERCHKU-1-token',
        )
        db.session.add(order)
        db.session.commit()

    payload = {
        'order_id': 'MERCHKU-1-token',
        'status_code': '200',
        'gross_amount': '75000.00',
        'transaction_status': 'settlement',
    }
    payload['signature_key'] = hashlib.sha512(
        b'MERCHKU-1-token20075000.00server-key'
    ).hexdigest()
    with app.test_client() as client:
        invalid = client.post('/pesanan/webhooks/midtrans', json={**payload, 'signature_key': 'bad'})
        assert invalid.status_code == 403
        response = client.post('/pesanan/webhooks/midtrans', json=payload)
        assert response.status_code == 200

    with app.app_context():
        order = Order.query.one()
        assert order.status == 'dibayar'


def test_biteship_rates_builds_request_from_saved_address(monkeypatch):
    from app.pesanan.integrations import biteship_rates

    calls = {}

    def fake_request(url, **kwargs):
        calls['url'] = url
        calls.update(kwargs)
        return {
            'pricing': [{
                'courier_code': 'jne',
                'courier_service_code': 'reg',
                'courier_service_name': 'REG',
                'price': 15000,
                'duration': '2-3 days',
            }],
        }

    monkeypatch.setattr('app.pesanan.integrations._request_json', fake_request)
    user = type('UserStub', (), {'postal_code': '40123'})()
    product = type('ProductStub', (), {
        'name': 'Kaos',
        'price': 75000,
        'weight_gram': 300,
        'is_active': True,
    })()
    cart_item = type('CartStub', (), {'product': product, 'quantity': 2})()
    rates = biteship_rates(
        {
            'BITESHIP_API_KEY': 'secret',
            'BITESHIP_BASE_URL': 'https://api.example.test',
            'SHIPPING_ORIGIN_POSTAL_CODE': '40124',
        },
        user,
        [cart_item],
    )
    assert rates[0]['key'] == 'jne|reg'
    assert calls['url'] == 'https://api.example.test/v1/rates/couriers'
    assert calls['payload']['destination_postal_code'] == '40123'
    assert calls['payload']['items'][0]['weight'] == 300
    assert calls['payload']['items'][0]['quantity'] == 2
