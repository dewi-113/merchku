"""
Test Tahap 5: Keranjang & Checkout

Kasus yang diuji:
1. IDOR keranjang — customer B tidak bisa ubah/hapus item milik customer A
2. IDOR pesanan  — customer B tidak bisa lihat/batalkan pesanan milik customer A
3. Manipulasi harga — harga di checkout diambil dari DB, bukan dari form
4. Oversell       — checkout melebihi stok ditolak, stok tidak negatif
5. Checkout kosong — tidak bisa checkout dengan keranjang kosong
6. Batalkan      — hanya status menunggu_pembayaran yang bisa dibatalkan oleh customer
"""

from app import db
from app.auth.models import User
from app.auth.security import hash_password
from app.katalog.models import Product, ProductSizeStock
from app.keranjang.models import CartItem
from app.pesanan.models import CUSTOMER_CANCELLABLE, Order, OrderItem
from tests.helpers import create_test_app

# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_app():
    return create_test_app()


def _seed(app):
    """Seed 2 customer, 1 produk tanpa ukuran (stok 5), 1 produk dengan ukuran (M stok 3)."""
    with app.app_context():
        # pastikan semua tabel ada (SQLite in-memory per app instance)
        db.create_all()
        # bersih
        OrderItem.query.delete()
        Order.query.delete()
        CartItem.query.delete()
        ProductSizeStock.query.delete()
        Product.query.delete()
        User.query.delete()
        db.session.commit()

        u1 = User(
            email='a@t.test',
            password_hash=hash_password('Password111'),
            role='customer',
            is_active=True,
            recipient_name='Test User',
            address='Jl. Test',
            address_label='rumah',
            district='Coblong',
            city='Bandung',
            postal_code='40123',
            province='Jawa Barat',
            phone='08111111111',
        )
        u2 = User(
            email='b@t.test',
            password_hash=hash_password('Password222'),
            role='customer',
            is_active=True,
            recipient_name='Test User',
            address='Jl. Test',
            address_label='rumah',
            district='Coblong',
            city='Bandung',
            postal_code='40123',
            province='Jawa Barat',
            phone='08111111111',
        )
        db.session.add_all([u1, u2])
        db.session.flush()

        p_plain = Product(name='Kaos Polos', description='', category='kaos',
                          price=75000, is_active=True, use_sizes=False, stock=5)
        p_sized = Product(name='Hoodie', description='', category='hoodie',
                          price=200000, is_active=True, use_sizes=True, stock=0)
        db.session.add_all([p_plain, p_sized])
        db.session.flush()

        ss_m = ProductSizeStock(product_id=p_sized.id, size='M', stock=3)
        db.session.add(ss_m)
        db.session.commit()

        return u1.id, u2.id, p_plain.id, p_sized.id


def test_pembeli_bisa_tambah_produk_dari_detail_ke_keranjang():
    app = _make_app()
    u1_id, _, p_plain_id, p_sized_id = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})

        plain_detail = c.get(f'/katalog/{p_plain_id}')
        assert plain_detail.status_code == 200
        assert b'Tambah ke Keranjang' in plain_detail.data
        added_plain = c.post(
            '/keranjang/tambah',
            data={'product_id': str(p_plain_id), 'quantity': '2'},
        )
        assert added_plain.status_code == 302
        assert added_plain.headers['Location'].endswith('/keranjang/')

        sized_detail = c.get(f'/katalog/{p_sized_id}')
        assert sized_detail.status_code == 200
        assert b'Pilih ukuran yang tersedia' in sized_detail.data
        assert b'type=\'radio\' name=\'size\' value=\'M\'' in sized_detail.data
        assert b'3 tersedia' in sized_detail.data
        added_sized = c.post(
            '/keranjang/tambah',
            data={'product_id': str(p_sized_id), 'size': 'M', 'quantity': '1'},
        )
        assert added_sized.status_code == 302

        cart = c.get('/keranjang/')
        assert cart.status_code == 200
        assert b'Keranjang Belanja' in cart.data
        assert b'Kaos Polos' in cart.data
        assert b'Hoodie' in cart.data
        assert b'data-cart-step=\'-1\'' in cart.data
        assert b'data-cart-step=\'1\'' in cart.data
        assert b'Ringkasan belanja' in cart.data

    with app.app_context():
        cart_items = CartItem.query.filter_by(user_id=u1_id).all()
        assert len(cart_items) == 2
        assert {(item.product_id, item.size, item.quantity) for item in cart_items} == {
            (p_plain_id, None, 2),
            (p_sized_id, 'M', 1),
        }


def test_keranjang_kosong_menampilkan_ajakan_belanja():
    app = _make_app()
    _seed(app)
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        response = c.get('/keranjang/')
        assert response.status_code == 200
        assert b'Belum ada produk di keranjang' in response.data
        assert b'Jelajahi katalog' in response.data


# ─── 1. IDOR keranjang ────────────────────────────────────────────────────────

def test_idor_cart_ubah():
    """Customer B tidak boleh mengubah item keranjang milik A."""
    app = _make_app()
    u1_id, _u2_id, p_id, _ = _seed(app)

    # A tambah item ke keranjang
    with app.app_context():
        item = CartItem(user_id=u1_id, product_id=p_id, size=None, quantity=1)
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    with app.test_client() as c:
        # login sebagai B
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Password222'})
        r = c.post(f'/keranjang/ubah/{item_id}', data={'quantity': 3})
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


def test_idor_cart_hapus():
    """Customer B tidak boleh menghapus item keranjang milik A."""
    app = _make_app()
    u1_id, _u2_id, p_id, _ = _seed(app)

    with app.app_context():
        item = CartItem(user_id=u1_id, product_id=p_id, size=None, quantity=1)
        db.session.add(item)
        db.session.commit()
        item_id = item.id

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Password222'})
        r = c.post(f'/keranjang/hapus/{item_id}')
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'

        # pastikan item masih ada
        with app.app_context():
            assert CartItem.query.get(item_id) is not None


# ─── 2. IDOR pesanan ─────────────────────────────────────────────────────────

def _create_order_for_user(app, user_id, product_id):
    """Buat order langsung di DB untuk user tertentu."""
    with app.app_context():
        order = Order(
            user_id=user_id,
            status='menunggu_pembayaran',
            recipient_name='Test User',
            address='Jl. Test No.1',
            phone='08123456789',
            total_price=75000,
        )
        db.session.add(order)
        db.session.flush()
        oi = OrderItem(
            order_id=order.id,
            product_id=product_id,
            product_name='Kaos Polos',
            size=None,
            quantity=1,
            unit_price=75000,
        )
        db.session.add(oi)
        db.session.commit()
        return order.id


def test_idor_order_detail():
    """Customer B tidak boleh melihat detail pesanan milik A."""
    app = _make_app()
    u1_id, _u2_id, p_id, _ = _seed(app)
    order_id = _create_order_for_user(app, u1_id, p_id)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Password222'})
        r = c.get(f'/pesanan/{order_id}')
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'


def test_riwayat_pesanan_marketplace_cards_and_status_filter():
    app = _make_app()
    user_id, _other_id, product_id, _sized_product_id = _seed(app)
    order_id = _create_order_for_user(app, user_id, product_id)

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        history = client.get('/pesanan/')
        assert history.status_code == 200
        assert b'Pesanan Saya' in history.data
        assert b'order-card' in history.data
        assert b'Kaos Polos' in history.data
        assert b'Menunggu pembayaran' in history.data
        assert b'Lihat detail' in history.data

        filtered = client.get('/pesanan/?status=menunggu_pembayaran')
        assert filtered.status_code == 200
        assert b'order-filter active' in filtered.data
        assert client.get(f'/pesanan/{order_id}').status_code == 200


def test_qris_demo_shows_reference_without_claiming_real_qris_payment():
    app = _make_app()
    user_id, _other_id, product_id, _sized_product_id = _seed(app)
    order_id = _create_order_for_user(app, user_id, product_id)
    with app.app_context():
        order = db.session.get(Order, order_id)
        order.payment_method = 'qris'
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        detail = client.get(f'/pesanan/{order_id}')
        assert detail.status_code == 200
        assert b'MERCHKU-QRIS-000001' in detail.data
        assert b'images/qris-demo.png' in detail.data
        assert b'tidak dapat dipindai' in detail.data

        payment = client.get(f'/pesanan/{order_id}/upload-bukti')
        assert payment.status_code == 200
        assert b'images/qris-demo.png' in payment.data

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.status == 'menunggu_pembayaran'
        assert order.payment_proof is None


def test_transfer_demo_menampilkan_bank_dan_virtual_account_fiktif():
    app = _make_app()
    user_id, _other_id, product_id, _sized_product_id = _seed(app)
    order_id = _create_order_for_user(app, user_id, product_id)
    with app.app_context():
        order = db.session.get(Order, order_id)
        order.payment_method = 'bank_transfer'
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        for url in (f'/pesanan/{order_id}', f'/pesanan/{order_id}/upload-bukti'):
            page = client.get(url)
            assert page.status_code == 200
            assert b'Bank Demo Merchku' in page.data
            assert b'8808 0000 0000 0001' in page.data
            assert b'MODE DEMO' in page.data


def test_idor_order_batalkan():
    """Customer B tidak boleh membatalkan pesanan milik A."""
    app = _make_app()
    u1_id, _u2_id, p_id, _ = _seed(app)
    order_id = _create_order_for_user(app, u1_id, p_id)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'b@t.test', 'password': 'Password222'})
        r = c.post(f'/pesanan/{order_id}/batalkan')
        assert r.status_code == 403, f'Expected 403, got {r.status_code}'

        # status tidak berubah
        with app.app_context():
            order = db.session.get(Order, order_id)
            assert order.status == 'menunggu_pembayaran'


# ─── 3. Manipulasi harga ─────────────────────────────────────────────────────

def test_harga_dari_db_bukan_form():
    """
    Checkout tidak menerima harga dari form.
    Total yang disimpan = harga dari DB * qty, bukan nilai yang dikirim client.
    """
    app = _make_app()
    u1_id, _, p_id, _ = _seed(app)

    # Tambah item ke keranjang
    with app.app_context():
        item = CartItem(user_id=u1_id, product_id=p_id, size=None, quantity=2)
        db.session.add(item)
        db.session.commit()

    with app.app_context():
        harga_db = db.session.get(Product, p_id).price  # 75000

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        # kirim "harga" palsu lewat form — server harus mengabaikannya
        r = c.post('/pesanan/checkout', data={
            'courier': 'jnt',
            'payment_method': 'qris',
            'recipient_name': 'Alamat palsu',
            'address': 'Alamat palsu',
            'phone': '08000000000',
            'price': '1',          # manipulasi harga
            'total_price': '100',  # manipulasi total
        }, follow_redirects=False)

        # harus redirect ke halaman detail pesanan (302)
        assert r.status_code == 302

    with app.app_context():
        order = Order.query.filter_by(user_id=u1_id).first()
        assert order is not None
        # total = harga_db * qty = 75000 * 2
        assert order.total_price == harga_db * 2, (
            f'Total seharusnya {harga_db * 2}, dapat {order.total_price}'
        )
        assert order.courier == 'jnt'
        assert order.payment_method == 'qris'
        assert order.recipient_name == 'Test User'
        assert order.address == 'Jl. Test'
        assert order.phone == '08111111111'
        assert order.district == 'Coblong'
        assert order.province == 'Jawa Barat'


def test_checkout_cod_dapat_dikonfirmasi_admin_sebelum_dikirim():
    app = _make_app()
    user_id, _, product_id, _ = _seed(app)
    with app.app_context():
        db.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=1))
        db.session.commit()

    checkout = {
        'courier': 'sicepat',
        'payment_method': 'cod',
    }
    with app.app_context():
        user = db.session.get(User, user_id)
        user.recipient_name = 'Penerima Kos'
        user.address_label = 'kos'
        user.delivery_note = 'Titip satpam'
        db.session.commit()
    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        checkout_page = client.get('/pesanan/checkout')
        assert checkout_page.status_code == 200
        assert b'Jl. Test' in checkout_page.data
        assert b'08111111111' in checkout_page.data
        assert b'name="address"' not in checkout_page.data
        assert b'name="phone"' not in checkout_page.data
        assert b'QRIS' in checkout_page.data
        assert b'J&amp;T Express' in checkout_page.data
        response = client.post('/pesanan/checkout', data=checkout)
        assert response.status_code == 302
        order_id = int(response.location.rsplit('/', 1)[-1])
        detail_page = client.get(response.location)
        assert detail_page.status_code == 200
        assert b'Alamat (kos)' in detail_page.data
        assert b'Upload Bukti Bayar' not in detail_page.data
        upload_response = client.get(
            f'/pesanan/{order_id}/upload-bukti',
            follow_redirects=True,
        )
        assert b'jangan unggah bukti transfer' in upload_response.data.lower()

    with app.app_context():
        order = Order.query.filter_by(user_id=user_id).one()
        assert order.address_label == 'kos'
        assert order.district == 'Coblong'
        assert order.delivery_note == 'Titip satpam'
        assert order.recipient_name == 'Penerima Kos'
        assert order.courier == 'sicepat'
        assert order.payment_method == 'cod'
        assert order.display_status == 'menunggu_konfirmasi_cod'
        assert order.can_transition_to('dibayar')
        assert not order.can_transition_to('menunggu_verifikasi')
        order.status = 'dibayar'
        assert order.display_status == 'cod_dikonfirmasi'
        assert order.can_transition_to('dikirim')
        order.status = 'menunggu_pembayaran'
        admin = User(
            email='admin@t.test',
            password_hash=hash_password('Password333'),
            role='admin',
            is_active=True,
        )
        db.session.add(admin)
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'admin@t.test', 'password': 'Password333'})
        admin_page = client.get(f'/admin/pesanan/{order_id}')
        assert admin_page.status_code == 200
        assert b'Konfirmasi COD / siap dikirim' in admin_page.data
        assert b'SiCepat' in admin_page.data


# ─── 4. Oversell ─────────────────────────────────────────────────────────────

def test_checkout_tidak_oversell():
    """
    Checkout dengan qty melebihi stok harus gagal dan stok tidak negatif.
    """
    app = _make_app()
    u1_id, _, p_id, _ = _seed(app)  # stok p_plain = 5

    # Set qty keranjang melebihi stok langsung di DB
    with app.app_context():
        item = CartItem(user_id=u1_id, product_id=p_id, size=None, quantity=99)
        db.session.add(item)
        db.session.commit()

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        r = c.post('/pesanan/checkout', data={
            'courier': 'jne',
            'payment_method': 'bank_transfer',
        }, follow_redirects=True)

        # harus redirect ke keranjang dengan pesan error, bukan buat order
        assert r.status_code == 200

    with app.app_context():
        # tidak ada order yang dibuat
        assert Order.query.filter_by(user_id=u1_id).count() == 0
        # stok tidak berkurang
        p = db.session.get(Product, p_id)
        assert p.stock >= 0, 'Stok tidak boleh negatif'
        assert p.stock == 5, f'Stok seharusnya tetap 5, dapat {p.stock}'


def test_checkout_sized_tidak_oversell():
    """Checkout ukuran dengan qty melebihi stok ukuran harus gagal."""
    app = _make_app()
    u1_id, _, _, p_sized_id = _seed(app)  # M stok 3

    with app.app_context():
        item = CartItem(user_id=u1_id, product_id=p_sized_id, size='M', quantity=10)
        db.session.add(item)
        db.session.commit()

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        c.post('/pesanan/checkout', data={
            'courier': 'jne',
            'payment_method': 'bank_transfer',
        }, follow_redirects=True)

    with app.app_context():
        assert Order.query.filter_by(user_id=u1_id).count() == 0
        ss = ProductSizeStock.query.filter_by(product_id=p_sized_id, size='M').first()
        assert ss.stock == 3, f'Stok M seharusnya tetap 3, dapat {ss.stock}'


# ─── 5. Checkout keranjang kosong ────────────────────────────────────────────

def test_checkout_keranjang_kosong():
    """Checkout dengan keranjang kosong harus redirect, tidak membuat order."""
    app = _make_app()
    u1_id, _, _, _ = _seed(app)

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        r = c.post('/pesanan/checkout', data={}, follow_redirects=False)
        # redirect ke keranjang karena kosong
        assert r.status_code in (302, 200)

    with app.app_context():
        assert Order.query.filter_by(user_id=u1_id).count() == 0


def test_checkout_mengarahkan_ke_profil_jika_alamat_belum_lengkap():
    app = _make_app()
    user_id, _, product_id, _ = _seed(app)
    with app.app_context():
        user = db.session.get(User, user_id)
        user.address = None
        db.session.add(CartItem(user_id=user_id, product_id=product_id, quantity=1))
        db.session.commit()

    with app.test_client() as client:
        client.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        response = client.get('/pesanan/checkout', follow_redirects=False)
        assert response.status_code == 302
        assert response.headers['Location'].endswith('/profil/')

    with app.app_context():
        assert Order.query.filter_by(user_id=user_id).count() == 0


# ─── 6. Batalkan — batasan status ────────────────────────────────────────────

def test_batalkan_hanya_saat_menunggu_pembayaran():
    """
    Customer hanya bisa batalkan pesanan saat status menunggu_pembayaran.
    Status lain harus ditolak.
    """
    app = _make_app()
    u1_id, _, _p_id, _ = _seed(app)

    non_cancellable = [s for s in [
        'menunggu_verifikasi', 'dibayar', 'dikirim', 'selesai', 'dibatalkan'
    ] if s not in CUSTOMER_CANCELLABLE]

    for status in non_cancellable:
        with app.app_context():
            order = Order(
                user_id=u1_id,
                status=status,
                recipient_name='Test',
                address='Jl. Test',
                phone='081',
                total_price=75000,
            )
            db.session.add(order)
            db.session.commit()
            oid = order.id

        with app.test_client() as c:
            c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
            r = c.post(f'/pesanan/{oid}/batalkan', follow_redirects=True)
            # harus 200 (redirect ke detail) dengan pesan warning, status tidak berubah
            assert r.status_code == 200

        with app.app_context():
            o = db.session.get(Order, oid)
            assert o.status == status, f'Status seharusnya tetap {status}, dapat {o.status}'


def test_checkout_sebagian_hanya_item_terpilih():
    """Checkout ?item=<id>: hanya item terpilih jadi pesanan, sisanya tetap di keranjang."""
    app = _make_app()
    u1_id, _, p_plain, p_sized = _seed(app)
    with app.app_context():
        a = CartItem(user_id=u1_id, product_id=p_plain, size=None, quantity=1)
        b = CartItem(user_id=u1_id, product_id=p_sized, size='M', quantity=1)
        db.session.add_all([a, b])
        db.session.commit()
        a_id, b_id = a.id, b.id

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        page = c.get('/keranjang/')
        assert b'Pilih semua' in page.data and b'cartCheckoutForm' in page.data
        preview = c.get(f'/pesanan/checkout?item={a_id}')
        assert b'Kaos Polos' in preview.data and b'Hoodie' not in preview.data
        r = c.post(f'/pesanan/checkout?item={a_id}',
                   data={'courier': 'jne', 'payment_method': 'qris'})
        assert r.status_code == 302

    with app.app_context():
        order = Order.query.filter_by(user_id=u1_id).one()
        assert [it.product_id for it in order.items] == [p_plain]
        assert order.total_price == 75000
        remaining = [it.id for it in CartItem.query.filter_by(user_id=u1_id)]
        assert remaining == [b_id]


def test_checkout_item_milik_orang_lain_diabaikan():
    app = _make_app()
    _, u2_id, p_plain, _ = _seed(app)
    with app.app_context():
        other = CartItem(user_id=u2_id, product_id=p_plain, size=None, quantity=1)
        db.session.add(other)
        db.session.commit()
        other_id = other.id
    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        r = c.get(f'/pesanan/checkout?item={other_id}')
        assert r.status_code == 302  # keranjang sendiri kosong -> kembali ke keranjang
    with app.app_context():
        assert Order.query.count() == 0


def test_checkout_multi_toko_dipecah_satu_pesanan_per_toko():
    app = _make_app()
    u1_id, _, p_plain, p_sized = _seed(app)
    with app.app_context():
        s1 = User(email='s1@t.test', password_hash='x', role='seller', is_active=True)
        s2 = User(email='s2@t.test', password_hash='x', role='seller', is_active=True)
        db.session.add_all([s1, s2])
        db.session.flush()
        db.session.get(Product, p_plain).owner_id = s1.id
        db.session.get(Product, p_sized).owner_id = s2.id
        db.session.add_all([
            CartItem(user_id=u1_id, product_id=p_plain, size=None, quantity=2),
            CartItem(user_id=u1_id, product_id=p_sized, size='M', quantity=1),
        ])
        db.session.commit()
        s1_id, s2_id = s1.id, s2.id

    with app.test_client() as c:
        c.post('/auth/login', data={'email': 'a@t.test', 'password': 'Password111'})
        r = c.post('/pesanan/checkout', data={'courier': 'jne', 'payment_method': 'cod'})
        assert r.status_code == 302

    with app.app_context():
        orders = Order.query.filter_by(user_id=u1_id).order_by(Order.id).all()
        assert len(orders) == 2
        owners = [{it.product.owner_id for it in o.items} for o in orders]
        assert {s1_id} in owners and {s2_id} in owners
        assert sum(o.total_price for o in orders) == 75000 * 2 + 200000
        assert CartItem.query.filter_by(user_id=u1_id).count() == 0
