from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.chat.models import ChatMessage, ChatThread
from app.katalog.models import Product
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    with app.app_context():
        db.create_all()
        ChatMessage.query.delete()
        ChatThread.query.delete()
        Product.query.delete()
        User.query.delete()
        db.session.commit()
        customer = User(
            email='customer@chat.test',
            password_hash=hash_password('Customer12345'),
            role='customer',
            is_active=True,
        )
        seller = User(
            email='seller@chat.test',
            password_hash=hash_password('Seller12345'),
            role='seller',
            is_active=True,
        )
        outsider = User(
            email='outsider@chat.test',
            password_hash=hash_password('Outsider12345'),
            role='customer',
            is_active=True,
        )
        db.session.add_all([customer, seller, outsider])
        db.session.flush()
        product = Product(
            name='Kaos Chat',
            category='kaos',
            price=50000,
            is_active=True,
            owner_id=seller.id,
        )
        db.session.add(product)
        db.session.commit()
        return app, product.id, customer.id, seller.id, outsider.id


def test_customer_and_seller_can_exchange_messages():
    app, product_id, _customer_id, seller_id, _outsider_id = _make_app()
    with app.test_client() as customer_client:
        customer_client.post(
            '/auth/login',
            data={'email': 'customer@chat.test', 'password': 'Customer12345'},
        )
        response = customer_client.post(f'/chat/mulai/{product_id}')
        assert response.status_code == 302
        thread_url = response.headers['Location']
        response = customer_client.post(thread_url, data={'body': 'Apakah stok masih ada?'})
        assert response.status_code == 302
        thread_page = customer_client.get(thread_url)
        assert b'Apakah stok masih ada?' in thread_page.data
        assert b"class='chat-shell'" in thread_page.data
        assert b"class='chat-message-row is-mine'" in thread_page.data
        footer_brand = thread_page.data.index(b"class='footer-brand'")
        footer_copyright = thread_page.data.index(b'&copy; 2026 merchku - PBLRKS321')
        assert footer_brand < footer_copyright
        assert b"class='footer-links'" not in thread_page.data

    with app.app_context():
        thread_id = ChatThread.query.one().id

    with app.test_client() as seller_client:
        seller_client.post(
            '/auth/login',
            data={'email': 'seller@chat.test', 'password': 'Seller12345'},
        )
        assert b'Apakah stok masih ada?' in seller_client.get(f'/chat/{thread_id}').data
        seller_client.post(f'/chat/{thread_id}', data={'body': 'Stok masih tersedia.'})
        assert b'Stok masih tersedia.' in seller_client.get(f'/chat/{thread_id}').data

    with app.app_context():
        assert ChatMessage.query.count() == 2
        assert ChatThread.query.one().seller_id == seller_id


def test_other_customer_cannot_read_chat():
    app, product_id, _customer_id, _seller_id, _outsider_id = _make_app()
    with app.test_client() as customer_client:
        customer_client.post(
            '/auth/login',
            data={'email': 'customer@chat.test', 'password': 'Customer12345'},
        )
        customer_client.post(f'/chat/mulai/{product_id}')

    with app.app_context():
        thread_id = ChatThread.query.one().id

    with app.test_client() as outsider_client:
        outsider_client.post(
            '/auth/login',
            data={'email': 'outsider@chat.test', 'password': 'Outsider12345'},
        )
        assert outsider_client.get(f'/chat/{thread_id}').status_code == 403
