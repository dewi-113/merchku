from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product
from app.katalog.review_model import Review
from app.pesanan.models import Order, OrderItem
from tests.helpers import create_test_app


def _make_app():
    app = create_test_app()
    with app.app_context():
        db.drop_all()
        db.create_all()
        p = Product(
            name='Kaos Hitam',
            description='deskripsi',
            category='kaos',
            price=75000,
            is_active=True,
            use_sizes=False,
            stock=5,
        )
        u1 = User(
            email='u1@merchku.test',
            password_hash=hash_password('Pass12345678'),
            role='customer',
            is_active=True,
        )
        u2 = User(
            email='u2@merchku.test',
            password_hash=hash_password('Pass12345678'),
            role='customer',
            is_active=True,
        )
        db.session.add_all([p, u1, u2])
        db.session.commit()
        pid = p.id
    return app, pid


def test_catalog_and_product_detail_are_public_for_visitors_and_customers():
    app, product_id = _make_app()
    with app.test_client() as client:
        visitor_catalog = client.get('/katalog/')
        assert visitor_catalog.status_code == 200
        assert b'Kaos Hitam' in visitor_catalog.data
        assert f'/media/produk-foto/{product_id}'.encode() in visitor_catalog.data
        assert client.get(f'/katalog/{product_id}').status_code == 200

        login = client.post(
            '/auth/login',
            data={'email': 'u1@merchku.test', 'password': 'Pass12345678'},
        )
        assert login.status_code == 302
        customer_catalog = client.get('/katalog/')
        assert customer_catalog.status_code == 200
        assert b'Kaos Hitam' in customer_catalog.data
        assert f'/media/produk-foto/{product_id}'.encode() in customer_catalog.data
        assert client.get(f'/katalog/{product_id}').status_code == 200


def test_product_detail_shows_public_seller_profile_and_recommendations():
    app = create_test_app()
    with app.app_context():
        seller = User(
            email='seller@merchku.test',
            password_hash=hash_password('Pass12345678'),
            role='seller',
            shop_name='Toko Uji',
            shop_description='Deskripsi toko untuk pengunjung.',
            is_active=True,
        )
        db.session.add(seller)
        db.session.flush()
        products = [
            Product(
                name=f'Kaos demo {index}',
                description=f'Deskripsi produk {index}',
                category='kaos',
                product_type='Kaos regular fit',
                color='Navy',
                price=50000 + index,
                is_active=True,
                use_sizes=False,
                stock=3,
                owner_id=seller.id,
            )
            for index in range(5)
        ]
        db.session.add_all(products)
        db.session.commit()
        product_id = products[0].id
        seller_id = seller.id

    with app.test_client() as client:
        detail = client.get(f'/katalog/{product_id}')
        assert detail.status_code == 200
        assert b'Jenis: Kaos regular fit' in detail.data
        assert b'Warna: Navy' in detail.data
        assert b'Toko Uji' in detail.data
        assert b'Chat Penjual' in detail.data
        assert b'Produk yang mungkin kamu suka' in detail.data
        assert client.get(f'/katalog/toko/{seller_id}').status_code == 200
        shop = client.get(f'/katalog/toko/{seller_id}')
        assert b'Deskripsi toko untuk pengunjung.' in shop.data
        assert b'Kaos demo' in shop.data
        assert b'Official store di Merchku Store' in shop.data
        assert b'5</strong> produk' in shop.data


def test_product_reviews_render_as_buyer_cards_with_seller_replies():
    app = create_test_app()
    with app.app_context():
        seller = User(
            email='store@merchku.test',
            password_hash=hash_password('Pass12345678'),
            role='seller',
            shop_name='Toko Kartu',
            is_active=True,
        )
        customer = User(
            email='buyer@merchku.test',
            password_hash=hash_password('Pass12345678'),
            role='customer',
            is_active=True,
        )
        db.session.add_all([seller, customer])
        db.session.flush()
        product = Product(
            name='Hoodie Review',
            description='Produk uji',
            category='hoodie',
            price=100000,
            is_active=True,
            stock=2,
            owner_id=seller.id,
        )
        db.session.add(product)
        db.session.flush()
        review = Review(
            product_id=product.id,
            user_id=customer.id,
            rating=5,
            comment='Bahannya nyaman dan sesuai deskripsi.',
            seller_reply='Terima kasih sudah berbelanja di toko kami.',
        )
        db.session.add(review)
        db.session.commit()
        product_id = product.id

    with app.test_client() as client:
        response = client.get(f'/katalog/{product_id}')
        assert response.status_code == 200
        assert b"class='review-card'" in response.data
        assert b'Bahannya nyaman dan sesuai deskripsi.' in response.data
        assert b'Balasan Toko Kartu' in response.data
        assert b'Terima kasih sudah berbelanja di toko kami.' in response.data


def test_manual_product_photo_uses_product_id_filename_or_category_fallback(tmp_path):
    app, product_id = _make_app()
    app.config['PRODUCT_PHOTOS_DIR'] = str(tmp_path)
    folder = tmp_path / 'Kaos lengan pendek'
    folder.mkdir()
    image_data = b'manual product photo'
    (folder / '1792668892760.png').write_bytes(image_data)

    with app.test_client() as client:
        photo = client.get(f'/media/produk-foto/{product_id}')
        assert photo.status_code == 200
        assert photo.data == image_data
        assert photo.mimetype == 'image/png'
        assert photo.headers['X-Content-Type-Options'] == 'nosniff'
        photo.close()

        (folder / '1792668892760.png').unlink()
        fallback = client.get(f'/media/produk-foto/{product_id}', follow_redirects=True)
        assert fallback.status_code == 200
        assert fallback.mimetype == 'image/svg+xml'
        assert b'<svg' in fallback.data

        assert client.get('/media/produk-foto/9999').status_code == 404


def test_nested_photo_folders_for_hoodie_lanyard_pin_mug_and_notebook(tmp_path):
    app, _ = _make_app()
    app.config['PRODUCT_PHOTOS_DIR'] = str(tmp_path)
    from app.katalog.models import Product

    photo_products = [
        ('Hoodie Demo', 'hoodie', ('Hoodie-20261022T134752Z-1-001', 'Hoodie')),
        ('Lanyard Demo', 'lanyard', ('Lanyard-20261022T134629Z-1-001', 'Lanyard')),
        ('Pin Badge Set Demo', 'lainnya', ('Pin -20261022T134745Z-1-001', 'Pin')),
        ('Mug Kampus Demo', 'lainnya', ('Mug kampus-20261022T134613Z-1-001', 'Mug kampus')),
        ('Notebook A5 Demo', 'lainnya', ('Notebook a5-20261022T134615Z-1-001', 'Notebook a5')),
    ]
    product_ids = []
    with app.app_context():
        for name, category, folder_parts in photo_products:
            product = Product(
                name=name,
                description='Foto produk uji',
                category=category,
                price=10000,
                is_active=True,
                use_sizes=False,
                stock=1,
            )
            db.session.add(product)
            db.session.flush()
            product_ids.append((product.id, folder_parts))
            photo_directory = tmp_path.joinpath(*folder_parts)
            photo_directory.mkdir(parents=True)
            (photo_directory / 'photo.png').write_bytes(b'nested photo')
        db.session.commit()

    with app.test_client() as client:
        for product_id, _folder_parts in product_ids:
            response = client.get(f'/media/produk-foto/{product_id}')
            assert response.status_code == 200
            assert response.mimetype == 'image/png'
            assert response.data == b'nested photo'


def test_catalog_search_filter_and_pagination():
    app, _pid = _make_app()
    from app.katalog.models import Product

    with app.app_context():
        db.session.add_all([
            Product(
                name=f'Kaos tambahan {index}',
                description='produk pagination',
                category='kaos',
                price=10000 + index,
                is_active=True,
                use_sizes=False,
                stock=1,
            )
            for index in range(13)
        ])
        db.session.commit()

    with app.test_client() as c:
        r = c.get('/katalog/?q=kaos')
        assert r.status_code == 200
        assert b'Kaos tambahan' in r.data
        r = c.get('/katalog/?cat=kaos')
        assert r.status_code == 200
        r = c.get('/katalog/?minp=50000&maxp=80000')
        assert r.status_code == 200
        r = c.get('/katalog/?sort=termurah')
        assert r.status_code == 200
        page_two = c.get('/katalog/?page=2&cat=kaos&sort=termurah')
        assert page_two.status_code == 200
        assert b'2 / 2' in page_two.data
        assert b'page=1' in page_two.data


def test_product_detail_and_review():
    app, pid = _make_app()
    with app.test_client() as c:
        c.post(
            '/auth/login',
            data={'email': 'u1@merchku.test', 'password': 'Pass12345678'},
        )
        assert b'pesanan produk ini selesai' in c.get(f'/katalog/{pid}').data
        response = c.post(
            f'/katalog/{pid}',
            data={'rating': '5', 'comment': 'Tidak memenuhi syarat'},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b'Tidak memenuhi syarat' not in response.data
        with app.app_context():
            assert Review.query.count() == 0
            user = User.query.filter_by(email='u1@merchku.test').one()
            order = Order(
                user_id=user.id,
                status='selesai',
                recipient_name='Test',
                address='Jalan Test',
                city='Bandung',
                postal_code='40123',
                phone='08123456789',
                total_price=75000,
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=pid,
                product_name='Kaos Hitam',
                quantity=1,
                unit_price=75000,
            ))
            db.session.commit()
        r = c.post(
            f'/katalog/{pid}',
            data={'rating': '5', 'comment': 'Bagus'},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b'Bagus' in r.data
        r = c.post(
            f'/katalog/{pid}',
            data={'rating': '4', 'comment': 'Lagi'},
            follow_redirects=True,
        )
        assert b'sudah memberikan ulasan' in r.data
