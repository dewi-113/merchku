from app.auth.models import User
from app.katalog.models import Product
from app.pesanan.models import Order
from tests.helpers import create_test_app


def test_seed_demo_creates_checkout_ready_store_and_is_idempotent():
    app = create_test_app()
    runner = app.test_cli_runner()

    first_result = runner.invoke(args=['seed-demo'])
    assert first_result.exit_code == 0, first_result.output

    with app.app_context():
        seller = User.query.filter_by(email='seller@demo.test').one()
        customer = User.query.filter_by(email='customer1@demo.test').one()
        assert seller.role == 'seller'
        assert seller.shop_name == 'Merch Kampus Store'
        assert customer.has_shipping_details
        assert customer.postal_code == '40132'
        assert Product.query.filter_by(owner_id=seller.id, is_active=True).count() == 24
        assert all(product.weight_gram > 0 for product in Product.query.all())
        assert 'katun' in Product.query.filter_by(name='Kaos Kampus Classic').one().description
        shirt = Product.query.filter_by(name='Kaos Kampus Classic').one()
        mug = Product.query.filter_by(name='Mug Keramik Putih').one()
        assert shirt.product_type == 'Kaos regular fit'
        assert shirt.color == 'Hitam'
        assert mug.is_fragile is True
        first_product_count = Product.query.count()
        first_order_count = Order.query.count()

    second_result = runner.invoke(args=['seed-demo'])
    assert second_result.exit_code == 0, second_result.output
    with app.app_context():
        assert Product.query.count() == first_product_count
        assert Order.query.count() == first_order_count
    with app.test_client() as client:
        landing = client.get('/')
        catalog = client.get('/katalog/?page=2')
        assert landing.status_code == 200
        assert catalog.status_code == 200
        assert b'Kaos Kampus Classic' in landing.data + catalog.data
        assert b'class=\'product-card\'' in landing.data
        assert b'Cari berdasarkan kategori' not in landing.data
        assert b'Tersedia</div>' not in landing.data
        assert b'500+' not in landing.data
        assert b'KATALOG CONTOH' not in landing.data
