from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.chat.models import ChatThread
from app.katalog.models import Product
from app.pesanan.models import Order
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    with app.app_context():
        customer = User(email='cs@buyer.test', password_hash=hash_password('Customer12345'),
                        role='customer', is_active=True, recipient_name='Budi Santoso')
        other = User(email='lain@buyer.test', password_hash=hash_password('Customer12345'),
                     role='customer', is_active=True)
        seller = User(email='cs@seller.test', password_hash=hash_password('Seller12345'),
                      role='seller', is_active=True, shop_name='Toko CS')
        db.session.add_all([customer, other, seller])
        db.session.flush()
        hoodie = Product(name='Hoodie Hitam Polos', category='hoodie', price=150000,
                         original_price=200000, is_active=True, stock=5, owner_id=seller.id)
        mug = Product(name='Mug Keramik', category='lainnya', price=40000,
                      is_active=True, stock=3, owner_id=seller.id)
        db.session.add_all([hoodie, mug])
        db.session.flush()
        mine = Order(user_id=customer.id, status='dikirim', recipient_name='Budi', address='Jl. A',
                     phone='0812', total_price=150000)
        theirs = Order(user_id=other.id, status='selesai', recipient_name='Lain', address='Jl. B',
                       phone='0813', total_price=99000)
        db.session.add_all([mine, theirs])
        db.session.commit()
        return app, hoodie.id, mine.id, theirs.id


def _ask(client, message):
    response = client.post('/bantuan/tanya', json={'message': message, 'history': []})
    assert response.status_code == 200
    return response.get_json()


def test_discount_percent_and_form_validation():
    app, hoodie_id, _, _ = _make_app()
    with app.app_context():
        assert db.session.get(Product, hoodie_id).discount_percent == 25
        assert Product(name='x', price=100, original_price=None).discount_percent == 0
        assert Product(name='x', price=100, original_price=90).discount_percent == 0

    from app.admin.forms import ProductForm
    with app.test_request_context(method='POST', data={
        'name': 'Kaos', 'category': 'kaos', 'price': '50000', 'original_price': '40000', 'stock': '3',
    }):
        form = ProductForm()
        assert not form.validate()
        assert form.original_price.errors


def test_cs_page_and_basic_answers_for_guest():
    app, hoodie_id, _, _ = _make_app()
    with app.test_client() as client:
        page = client.get('/bantuan/')
        assert page.status_code == 200
        assert b'data-cs-root' in page.data

        assert 'Merchy' in _ask(client, 'halo')['reply']

        found = _ask(client, 'ada hoodie hitam?')
        assert [p['id'] for p in found['products']] == [hoodie_id]

        deals = _ask(client, 'ada promo diskon?')
        assert deals['products'][0]['discount'] == 25

        status = _ask(client, 'cek status pesanan saya')
        assert 'masuk' in status['reply'].lower()
        assert status['source'] == 'otomatis'

        assert client.post('/bantuan/tanya', json={'message': ''}).status_code == 400


def test_cs_only_shows_own_orders():
    app, _, mine_id, theirs_id = _make_app()
    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'cs@buyer.test', 'password': 'Customer12345'})
        reply = _ask(client, 'status pesanan saya')['reply']
        assert f'#{mine_id}' in reply
        assert 'Sedang dikirim' in reply
        snoop = _ask(client, f'status pesanan #{theirs_id}')['reply']
        assert f'#{theirs_id}' not in snoop


def test_chat_ajax_send_and_poll():
    app, hoodie_id, _, _ = _make_app()
    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'cs@buyer.test', 'password': 'Customer12345'})
        start = client.post(f'/chat/mulai/{hoodie_id}')
        assert start.status_code == 302
        room_url = start.headers['Location']
        assert f'produk={hoodie_id}' in room_url
        room = client.get(room_url)
        assert b'Hoodie Hitam Polos' in room.data  # kartu produk yang ditanyakan
        assert b'data-chat-room' in room.data

        with app.app_context():
            thread_id = ChatThread.query.one().id
        sent = client.post(f'/chat/{thread_id}', data={'body': 'Stok ready kak?'},
                           headers={'X-Requested-With': 'fetch'})
        assert sent.status_code == 200
        message = sent.get_json()['message']
        assert message['mine'] is True and message['body'] == 'Stok ready kak?'

        polled = client.get(f'/chat/{thread_id}/pesan?after=0').get_json()['messages']
        assert [m['body'] for m in polled] == ['Stok ready kak?']
        assert client.get(f'/chat/{thread_id}/pesan?after={message["id"]}').get_json()['messages'] == []

        empty = client.post(f'/chat/{thread_id}', data={'body': '  '}, headers={'X-Requested-With': 'fetch'})
        assert empty.status_code == 400

    with app.test_client() as outsider:
        outsider.post('/auth/login', data={'email': 'lain@buyer.test', 'password': 'Customer12345'})
        assert outsider.get(f'/chat/{thread_id}/pesan').status_code == 403


def test_landing_and_catalog_show_discounts():
    app, _, _, _ = _make_app()
    with app.test_client() as client:
        landing = client.get('/')
        assert b'Lagi Diskon' in landing.data
        assert b'25%' in landing.data
        catalog = client.get('/katalog/?sort=diskon')
        assert b'Hoodie Hitam Polos' in catalog.data
        assert b'Mug Keramik' not in catalog.data
