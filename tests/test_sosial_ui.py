from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.follow_model import ShopFollow
from app.katalog.models import Product
from app.katalog.review_model import Review
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    with app.app_context():
        customer = User(email='ikut@buyer.test', password_hash=hash_password('Customer12345'),
                        role='customer', is_active=True, recipient_name='Rizky Pratama')
        seller = User(email='ikut@seller.test', password_hash=hash_password('Seller12345'),
                      role='seller', is_active=True, shop_name='Toko Ikut')
        db.session.add_all([customer, seller])
        db.session.flush()
        product = Product(name='Kaos Hitam', category='kaos', price=90000,
                          is_active=True, stock=4, owner_id=seller.id)
        db.session.add(product)
        db.session.commit()
        return app, customer.id, seller.id, product.id


def _login(client, email, password):
    client.post('/auth/login', data={'email': email, 'password': password})


def test_customer_can_follow_and_unfollow_shop():
    app, customer_id, seller_id, _ = _make_app()
    with app.test_client() as client:
        _login(client, 'ikut@buyer.test', 'Customer12345')
        page = client.get(f'/katalog/toko/{seller_id}')
        assert b'+ Ikuti' in page.data
        assert b'0</strong> pengikut' in page.data

        client.post(f'/katalog/toko/{seller_id}/ikuti')
        page = client.get(f'/katalog/toko/{seller_id}')
        assert b'Mengikuti' in page.data
        assert b'1</strong> pengikut' in page.data

        client.post(f'/katalog/toko/{seller_id}/ikuti')
        with app.app_context():
            assert ShopFollow.query.filter_by(seller_id=seller_id, follower_id=customer_id).count() == 0


def test_seller_cannot_follow_and_next_is_not_open_redirect():
    app, _, seller_id, _ = _make_app()
    with app.test_client() as client:
        _login(client, 'ikut@seller.test', 'Seller12345')
        client.post(f'/katalog/toko/{seller_id}/ikuti')
        with app.app_context():
            assert ShopFollow.query.count() == 0
    with app.test_client() as client:
        _login(client, 'ikut@buyer.test', 'Customer12345')
        response = client.post(f'/katalog/toko/{seller_id}/ikuti', data={'next': '//evil.test/x'})
        assert response.headers['Location'].endswith(f'/katalog/toko/{seller_id}')


def test_review_shows_short_name_not_email():
    app, customer_id, _, product_id = _make_app()
    with app.app_context():
        db.session.add(Review(product_id=product_id, user_id=customer_id, rating=5, comment='Mantap'))
        db.session.commit()
    with app.test_client() as client:
        page = client.get(f'/katalog/{product_id}')
        assert b'Rizky P.' in page.data
        assert b'>ikut<' not in page.data


def test_profile_avatar_uses_plus_picker():
    app, _, _, _ = _make_app()
    with app.test_client() as client:
        _login(client, 'ikut@buyer.test', 'Customer12345')
        page = client.get('/profil/')
        assert b'data-avatar-form' in page.data
        assert b'profile-avatar-plus' in page.data
        assert b"accept='image/*'" in page.data or b'accept="image/*"' in page.data
        assert b'maksimum 1 MB' not in page.data
        assert b'maks 1 MB' not in page.data


def test_chat_room_has_no_safety_banner_and_landing_layout():
    app, _, _, product_id = _make_app()
    with app.test_client() as client:
        _login(client, 'ikut@buyer.test', 'Customer12345')
        room = client.get(client.post(f'/chat/mulai/{product_id}').headers['Location'])
        assert b'Demi keamanan' not in room.data
        assert b'data-chat-emoji' in room.data

        landing = client.get('/')
        assert b'promo-app' in landing.data
        assert b'Toko pilihan' not in landing.data
        assert b'Tote Bag</span>' not in landing.data  # kategori diringkas
        assert b'Almamater</span>' in landing.data
