import os

import click
from flask.cli import with_appcontext

from app import db
from app.auth.models import User
from app.auth.security import hash_password


@click.command('create-admin')
@click.option('--email', default='admin@merchku.test')
@click.option('--password', default='admin12345678')  # min 10
@with_appcontext
def create_admin(email, password):
    if len(password) < 10:
        raise click.BadParameter('password min 10')
    u = User.query.filter_by(email=email.lower()).first()
    if u:
        u.password_hash = hash_password(password)
        u.role = 'admin'
        u.is_active = True
        db.session.commit()
        click.echo('updated admin')
        return
    u = User(
        email=email.lower(),
        password_hash=hash_password(password),
        role='admin',
        is_active=True,
    )
    db.session.add(u)
    db.session.commit()
    click.echo('admin created')


@click.command('seed-demo')
@click.option('--force', is_flag=True, default=False, help='Jalankan di production (berbahaya).')
@with_appcontext
def seed_demo(force):
    """Isi data demo: admin, customer, produk, pesanan.

    Perintah ini menolak berjalan di ENV=prod kecuali diberi flag --force.
    Data yang sudah ada TIDAK dihapus — perintah ini idempoten (skip jika sudah ada).
    """
    from flask import current_app

    env = current_app.config.get('ENV', 'dev') or os.getenv('FLASK_ENV', 'dev')
    if env in ('prod', 'production') and not force:
        raise click.ClickException(
            'Seed-demo menolak berjalan di production. Gunakan --force jika yakin.'
        )

    # --- import model di sini agar tidak circular di top-level ---
    from app.katalog.models import SIZES, Product, ProductSizeStock

    click.echo('Seeding demo data...')

    # ── Admin ──────────────────────────────────────────────────────────────
    admin_email = 'admin@demo.test'
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            email=admin_email,
            password_hash=hash_password('AdminDemo1234'),
            role='admin',
            is_active=True,
        )
        db.session.add(admin)
        db.session.flush()
        click.echo(f'  [+] admin: {admin_email} / AdminDemo1234')
    else:
        click.echo(f'  [=] admin sudah ada: {admin_email}')

    # ── Customers ──────────────────────────────────────────────────────────
    customers = []
    for i in range(1, 4):
        email = f'customer{i}@demo.test'
        u = User.query.filter_by(email=email).first()
        if not u:
            u = User(
                email=email,
                password_hash=hash_password(f'Customer{i}Demo1'),
                role='customer',
                is_active=True,
            )
            db.session.add(u)
            db.session.flush()
            click.echo(f'  [+] customer: {email} / Customer{i}Demo1')
        else:
            click.echo(f'  [=] customer sudah ada: {email}')
        shipping_profile = {
            'recipient_name': f'Demo Customer {i}',
            'address': f'Jl. Demo Merdeka No. {10 + i}',
            'address_label': 'rumah',
            'district': 'Coblong',
            'city': 'Bandung',
            'postal_code': '40132',
            'province': 'Jawa Barat',
            'phone': f'08123456789{i}',
        }
        for field, value in shipping_profile.items():
            if not getattr(u, field):
                setattr(u, field, value)
        customers.append(u)

    # ── Penjual demo (dengan 8 produk miliknya) ────────────────────────────
    seller_email = 'seller@demo.test'
    seller = User.query.filter_by(email=seller_email).first()
    if not seller:
        seller = User(
            email=seller_email,
            password_hash=hash_password('SellerDemo1234'),
            role='seller',
            shop_name='Merch Kampus Store',
            shop_description='Toko demo merchandise kampus dengan pilihan produk apparel dan aksesori.',
            is_active=True,
        )
        db.session.add(seller)
        db.session.flush()
        click.echo(f'  [+] seller: {seller_email} / SellerDemo1234')
    else:
        click.echo(f'  [=] seller sudah ada: {seller_email}')
    seller.role = 'seller'
    seller.shop_name = seller.shop_name or 'Merch Kampus Store'
    if not seller.shop_description or '8 produk' in seller.shop_description:
        seller.shop_description = (
            'Toko demo merchandise kampus dengan pilihan produk apparel dan aksesori.'
        )
    seller.is_active = True

    seller_products_data = [
        ('Kaos Kampus Classic', 'kaos', 89000, 40, False),
        ('Hoodie Merchku Hitam', 'hoodie', 235000, 25, True),
        ('Jaket Harrington Krem', 'jaket', 385000, 12, True),
        ('Almet Kampus Edisi 2026', 'almet', 195000, 18, True),
        ('Tote Bag Kanvas Hitam', 'tote_bag', 68000, 30, False),
        ('Stiker Pack Merchku', 'stiker', 15000, 120, False),
        ('Lanyard Custom Merchku', 'lanyard', 32000, 55, False),
        ('Topi Baseball Hitam', 'lainnya', 75000, 20, False),
    ]
    demo_weights = {
        'kaos': 250,
        'hoodie': 700,
        'jaket': 800,
        'almet': 800,
        'tote_bag': 300,
        'stiker': 100,
        'lanyard': 100,
        'lainnya': 250,
    }
    demo_product_details = {
        'kaos': 'Bahan katun nyaman untuk kegiatan kampus dan pemakaian sehari-hari.',
        'hoodie': 'Bahan fleece hangat dengan potongan santai untuk aktivitas harian.',
        'jaket': 'Jaket bahan pilihan dengan jahitan rapi untuk kegiatan luar ruang.',
        'almet': 'Almamater bahan drill dengan potongan nyaman untuk kegiatan kampus.',
        'tote_bag': 'Tas kanvas praktis untuk membawa buku dan perlengkapan harian.',
        'stiker': 'Stiker merchandise dengan desain kampus, cocok untuk laptop dan tumbler.',
        'lanyard': 'Tali lanyard kuat untuk kartu identitas dan kunci.',
        'lainnya': 'Merchandise pilihan dengan desain bertema kampus.',
    }

    def product_description(name, category):
        if name == 'Mug Keramik Putih':
            return f'{name}. Mug keramik untuk minuman hangat dan dingin.'
        return f'{name}. {demo_product_details[category]}'

    demo_clothing_details = {
        'Kaos Kampus Classic': ('Kaos regular fit', 'Hitam'),
        'Kaos Komunitas Navy': ('Kaos regular fit', 'Putih'),
        'Hoodie Merchku Hitam': ('Hoodie fleece', 'Navy'),
        'Hoodie Polos Krem': ('Hoodie pullover', 'Abu-abu'),
        'Hoodie Polos Navy': ('Hoodie fleece printing', 'Hitam'),
        'Jaket Harrington Krem': ('Jaket varsity', 'Navy / putih'),
        'Jaket Bomber Navy': ('Jaket varsity', 'Navy / putih'),
        'Jaket Harrington Putih': ('Jaket bomber', 'Hitam'),
        'Almet Kampus Edisi 2026': ('Jas almamater', 'Navy'),
        'Almet Kampus Merah 2026': ('Jas almamater', 'Navy'),
    }

    def demo_product_attributes(name, category):
        fixed = {new: (kind, color) for new, kind, color in PRODUCT_FIXES.values()}
        product_type, color = fixed.get(name) or demo_clothing_details.get(name, (None, None))
        fragile = name == 'Mug Keramik Putih'
        return product_type, color, fragile

    for name, cat, price, stock, use_sizes in seller_products_data:
        p = Product.query.filter_by(name=name).first()
        product_type, color, is_fragile = demo_product_attributes(name, cat)
        if not p:
            p = Product(
                name=name,
                description=product_description(name, cat),
                category=cat,
                product_type=product_type,
                color=color,
                price=price,
                weight_gram=demo_weights[cat],
                is_fragile=is_fragile,
                is_active=True,
                use_sizes=use_sizes,
                stock=0 if use_sizes else stock,
                owner_id=seller.id,
            )
            db.session.add(p)
            db.session.flush()
            if use_sizes:
                for size in SIZES:
                    stok_size = {'S': 4, 'M': 8, 'L': 6, 'XL': 5, 'XXL': 2}[size]
                    db.session.add(ProductSizeStock(
                        product_id=p.id, size=size, stock=stok_size,
                    ))
            click.echo(f'  [+] produk penjual: {name}')
        else:
            if p.owner_id is None:
                p.owner_id = seller.id
                click.echo(f'  [~] produk penjual diadopsi: {name}')
            else:
                click.echo(f'  [=] produk penjual sudah ada: {name}')
            if p.weight_gram in (None, 500):
                p.weight_gram = demo_weights[cat]
            if not p.description or 'produk demo dari' in p.description.lower():
                p.description = product_description(name, cat)
            p.product_type = p.product_type or product_type
            p.color = p.color or color
            p.is_fragile = p.is_fragile or is_fragile

    # ── Produk tanpa ukuran (10 produk) ────────────────────────────────────
    plain_products_data = [
        ('Stiker Kampus A', 'stiker', 15000, 50),
        ('Stiker Logo B', 'stiker', 12000, 80),
        ('Lanyard Polos Krem', 'lanyard', 25000, 30),
        ('Lanyard Custom Krem', 'lanyard', 35000, 20),
        ('Tote Bag Kanvas Hijau Army', 'tote_bag', 65000, 15),
        ('Tote Bag Kanvas Putih', 'tote_bag', 75000, 10),
        ('Pin Bulat Putih', 'lainnya', 20000, 100),
        ('Notebook A5 Krem', 'lainnya', 30000, 40),
        ('Mug Keramik Putih', 'lainnya', 55000, 25),
        ('Gantungan Kunci Akrilik', 'lainnya', 18000, 60),
    ]

    plain_products = []
    for name, cat, price, stock in plain_products_data:
        p = Product.query.filter_by(name=name).first()
        product_type, color, is_fragile = demo_product_attributes(name, cat)
        if not p:
            p = Product(
                name=name, description=product_description(name, cat),
                category=cat, product_type=product_type, color=color, price=price,
                weight_gram=demo_weights[cat],
                is_fragile=is_fragile,
                is_active=True, use_sizes=False, stock=stock,
                owner_id=seller.id,
            )
            db.session.add(p)
            db.session.flush()
            click.echo(f'  [+] produk: {name} (stok {stock})')
        else:
            if p.owner_id is None:
                p.owner_id = seller.id
            if p.weight_gram in (None, 500):
                p.weight_gram = demo_weights[cat]
            if not p.description or p.description.startswith('Demo produk '):
                p.description = product_description(name, cat)
            p.product_type = p.product_type or product_type
            p.color = p.color or color
            p.is_fragile = p.is_fragile or is_fragile
            click.echo(f'  [=] produk sudah ada: {name}')
        plain_products.append(p)

    # ── Produk dengan ukuran (6 produk) ────────────────────────────────────
    sized_products_data = [
        ('Almet Kampus Merah 2026', 'almet', 185000),
        ('Kaos Komunitas Navy', 'kaos', 95000),
        ('Hoodie Polos Krem', 'hoodie', 250000),
        ('Hoodie Polos Navy', 'hoodie', 285000),
        ('Jaket Bomber Navy', 'jaket', 375000),
        ('Jaket Harrington Putih', 'jaket', 345000),
    ]

    sized_products = []
    for name, cat, price in sized_products_data:
        p = Product.query.filter_by(name=name).first()
        product_type, color, is_fragile = demo_product_attributes(name, cat)
        if not p:
            p = Product(
                name=name, description=product_description(name, cat),
                category=cat, product_type=product_type, color=color, price=price,
                weight_gram=demo_weights[cat],
                is_fragile=is_fragile,
                is_active=True, use_sizes=True, stock=0,
                owner_id=seller.id,
            )
            db.session.add(p)
            db.session.flush()
            for size in SIZES:
                stok_size = {'S': 5, 'M': 10, 'L': 8, 'XL': 6, 'XXL': 3}[size]
                db.session.add(ProductSizeStock(
                    product_id=p.id, size=size, stock=stok_size,
                ))
            click.echo(f'  [+] produk berukuran: {name}')
        else:
            if p.owner_id is None:
                p.owner_id = seller.id
            if p.weight_gram in (None, 500):
                p.weight_gram = demo_weights[cat]
            if not p.description or p.description.startswith('Demo produk '):
                p.description = product_description(name, cat)
            p.product_type = p.product_type or product_type
            p.color = p.color or color
            p.is_fragile = p.is_fragile or is_fragile
            click.echo(f'  [=] produk sudah ada: {name}')
        sized_products.append(p)

    db.session.flush()

    # ── Beberapa pesanan demo ───────────────────────────────────────────────
    # Pesanan 1: customer1 — sudah selesai
    _make_demo_order(
        customers[0],
        [(plain_products[0], None, 2), (plain_products[2], None, 1)],
        status='selesai',
    )

    # Pesanan 2: customer1 — menunggu pembayaran
    _make_demo_order(
        customers[0],
        [(sized_products[0], 'M', 1), (plain_products[4], None, 1)],
        status='menunggu_pembayaran',
    )

    # Pesanan 3: customer2 — menunggu verifikasi
    _make_demo_order(
        customers[1],
        [(sized_products[1], 'L', 2)],
        status='menunggu_verifikasi',
    )

    # Pesanan 4: customer2 — dikirim
    _make_demo_order(
        customers[1],
        [(sized_products[2], 'M', 1), (plain_products[6], None, 3)],
        status='dikirim',
    )

    # Pesanan 5: customer3 — dibatalkan
    _make_demo_order(
        customers[2],
        [(plain_products[8], None, 1)],
        status='dibatalkan',
    )

    db.session.commit()
    click.echo('\nSeed demo selesai.')
    click.echo('Login admin : admin@demo.test / AdminDemo1234')
    click.echo('Login cust  : customer1@demo.test / Customer1Demo1')
    click.echo('Login seller: seller@demo.test / SellerDemo1234')


EXTRA_SHOPS = [
    {
        'email': 'ruangkreatif@demo.test',
        'password': 'RuangKreatif123',
        'shop_name': 'Ruang Kreatif Merch',
        'shop_description': (
            'Merchandise bergaya streetwear dengan nuansa senja: hoodie oversize, '
            'kaos grafis, dan aksesori harian.'
        ),
        'palette': ('#3b1d0f', '#d9733b', '#ffe6cc'),
        'products': [
            ('Hoodie Oversize Senja', 'hoodie', 259000, 0, True, 'hoodie', 1,
             'Hoodie oversize', 'Peach'),
            ('Kaos Grafis Ruang Kreatif', 'kaos', 99000, 0, True, 'kaos_pendek', 1,
             'Kaos oversize', 'Cokelat'),
            ('Tote Bag Ruang Kreatif', 'tote_bag', 72000, 25, False, 'totebag', 1, None, 'Cokelat'),
            ('Topi Dad Hat Senja', 'lainnya', 79000, 18, False, 'topi', 1, 'Dad hat', 'Krem'),
            ('Stiker Vinyl Pack Kreatif', 'stiker', 18000, 150, False, 'stiker', 1, None, None),
            ('Mug Enamel Ruang Kreatif', 'lainnya', 65000, 20, False, 'mug', 0, 'Mug enamel', 'Krem'),
        ],
    },
    {
        'email': 'himpunanstore@demo.test',
        'password': 'HimpunanStore123',
        'shop_name': 'Himpunan Store',
        'shop_description': (
            'Toko resmi merchandise himpunan mahasiswa. Jaket, kaos, dan atribut '
            'organisasi dengan warna hijau khas himpunan.'
        ),
        'palette': ('#0b2e22', '#2f9e6f', '#e0f7ea'),
        'products': [
            ('Jaket Coach Himpunan', 'jaket', 329000, 0, True, 'jaket', 1, 'Jaket coach', 'Hijau tua'),
            ('Kaos Lengan Panjang Himpunan', 'kaos', 119000, 0, True, 'kaos_panjang', 1,
             'Kaos lengan panjang', 'Hijau'),
            ('Lanyard Himpunan Hijau', 'lanyard', 30000, 80, False, 'lanyard', 0, None, 'Hijau'),
            ('Pin Enamel Himpunan', 'lainnya', 25000, 90, False, 'pin', 1, 'Pin enamel', None),
            ('Notebook Dot Grid Himpunan', 'lainnya', 35000, 45, False, 'notebook', 0,
             'Notebook A5 dot grid', None),
        ],
    },
    {
        'email': 'runclub@demo.test',
        'password': 'KampusRunClub123',
        'shop_name': 'Kampus Run Club',
        'shop_description': (
            'Perlengkapan dan merchandise komunitas lari kampus. Bahan ringan, '
            'nyaman dipakai latihan maupun nongkrong.'
        ),
        'palette': ('#15112e', '#6d5dfc', '#ecebff'),
        'products': [
            ('Kaos Dry-Fit Run Club', 'kaos', 109000, 0, True, 'kaos_pendek', 2,
             'Kaos dry-fit', 'Navy ungu'),
            ('Hoodie Run Club Night', 'hoodie', 245000, 0, True, 'hoodie', 2, 'Hoodie fleece', 'Navy ungu'),
            ('Topi Running Run Club', 'lainnya', 85000, 22, False, 'topi', 2, 'Topi running', 'Putih'),
            ('Gantungan Kunci Medali', 'lainnya', 22000, 70, False, 'gantungan_kunci', 1, None, 'Hitam'),
            ('Tote Bag Race Pack', 'tote_bag', 69000, 30, False, 'totebag', 2, None, 'Putih'),
        ],
    },
]

_EXTRA_WEIGHTS = {
    'kaos': 250, 'hoodie': 700, 'jaket': 800, 'almet': 800,
    'tote_bag': 300, 'stiker': 100, 'lanyard': 100, 'lainnya': 250,
}


def _load_font(size, bold=False):
    from PIL import ImageFont

    names = (
        ('segoeuib.ttf', 'arialbd.ttf', 'DejaVuSans-Bold.ttf')
        if bold else ('segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf')
    )
    for name in names:
        for path in (name, os.path.join('C:\\Windows\\Fonts', name),
                     os.path.join('/usr/share/fonts/truetype/dejavu', name)):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _render_shop_photo(source, palette, shop_name, product_name, target):
    """Buat foto produk bernuansa warna toko dari foto dasar di product_photos."""
    from PIL import Image, ImageDraw, ImageOps

    with Image.open(source) as image:
        image = image.convert('RGBA')
        base = Image.new('RGB', image.size, (255, 255, 255))
        base.paste(image, mask=image.getchannel('A'))
    width, height = 900, 1125
    base = ImageOps.fit(base, (width, height), centering=(0.5, 0.55))
    dark, mid, light = palette
    toned = ImageOps.colorize(ImageOps.grayscale(base), black=dark, mid=mid, white=light)
    photo = Image.blend(toned, base, 0.12)

    overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for row in range(260):
        alpha = int(190 * (row / 260) ** 1.6)
        draw.line([(0, height - 260 + row), (width, height - 260 + row)], fill=(10, 10, 20, alpha))
    photo = Image.alpha_composite(photo.convert('RGBA'), overlay)

    draw = ImageDraw.Draw(photo)
    badge_font = _load_font(30, bold=True)
    title_font = _load_font(46, bold=True)
    badge = shop_name.upper()
    bbox = draw.textbbox((0, 0), badge, font=badge_font)
    badge_w, badge_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.rounded_rectangle(
        [36, 36, 36 + badge_w + 44, 36 + badge_h + 30], radius=28, fill=light,
    )
    draw.text((58, 36 + 15 - bbox[1]), badge, font=badge_font, fill=dark)
    draw.text((48, height - 104), product_name, font=title_font, fill='#ffffff')
    photo.convert('RGB').save(target, 'JPEG', quality=84, optimize=True, progressive=True)


@click.command('seed-toko')
@click.option('--force', is_flag=True, default=False, help='Jalankan di production (berbahaya).')
@click.option('--regen-images', is_flag=True, default=False, help='Buat ulang gambar produk.')
@with_appcontext
def seed_toko(force, regen_images):
    """Tambah beberapa toko demo lain beserta produk dan gambarnya (idempoten)."""
    import uuid

    from flask import current_app

    from app.core.routes import (
        _PRODUCT_PHOTO_FOLDERS,
        list_photos,
        resolve_photo_directory,
    )
    from app.katalog.models import SIZES, Product, ProductSizeStock

    env = current_app.config.get('ENV', 'dev') or os.getenv('FLASK_ENV', 'dev')
    if env in ('prod', 'production') and not force:
        raise click.ClickException(
            'seed-toko menolak berjalan di production. Gunakan --force jika yakin.'
        )

    photos_dir = current_app.config['PRODUCT_PHOTOS_DIR']
    upload_dir = current_app.config['UPLOAD_PUBLIC']
    os.makedirs(upload_dir, exist_ok=True)

    def source_photo(folder_key, index):
        folder = resolve_photo_directory(photos_dir, _PRODUCT_PHOTO_FOLDERS[folder_key])
        photos = list_photos(folder) if folder else []
        return os.path.join(folder, photos[index % len(photos)]) if photos else None

    for shop in EXTRA_SHOPS:
        seller = User.query.filter_by(email=shop['email']).first()
        if not seller:
            seller = User(
                email=shop['email'],
                password_hash=hash_password(shop['password']),
                role='seller',
                is_active=True,
            )
            db.session.add(seller)
            click.echo(f"  [+] toko: {shop['shop_name']} ({shop['email']} / {shop['password']})")
        else:
            click.echo(f"  [=] toko sudah ada: {shop['shop_name']}")
        seller.role = 'seller'
        seller.shop_name = seller.shop_name or shop['shop_name']
        seller.shop_description = seller.shop_description or shop['shop_description']
        seller.is_active = True
        db.session.flush()

        for (name, cat, price, stock, use_sizes, folder_key, photo_index,
             product_type, color) in shop['products']:
            product = Product.query.filter_by(name=name).first()
            if not product:
                product = Product(
                    name=name,
                    description=(
                        f"{name}. Produk resmi dari {shop['shop_name']}. "
                        f"{shop['shop_description']}"
                    ),
                    category=cat,
                    product_type=product_type,
                    color=color,
                    price=price,
                    weight_gram=_EXTRA_WEIGHTS[cat],
                    is_fragile='mug' in name.lower(),
                    is_active=True,
                    use_sizes=use_sizes,
                    stock=0 if use_sizes else stock,
                    owner_id=seller.id,
                )
                db.session.add(product)
                db.session.flush()
                if use_sizes:
                    for size in SIZES:
                        db.session.add(ProductSizeStock(
                            product_id=product.id, size=size,
                            stock={'S': 6, 'M': 12, 'L': 10, 'XL': 6, 'XXL': 3}[size],
                        ))
                click.echo(f'      [+] produk: {name}')
            elif product.owner_id is None:
                product.owner_id = seller.id

            has_image = product.image and os.path.isfile(os.path.join(upload_dir, product.image))
            if has_image and not regen_images:
                continue
            source = source_photo(folder_key, photo_index)
            if not source:
                click.echo(f'      [!] foto dasar tidak ditemukan untuk {name}, pakai foto kategori')
                continue
            filename = product.image if has_image else f'{uuid.uuid4().hex}.jpg'
            try:
                _render_shop_photo(
                    source, shop['palette'], shop['shop_name'], name,
                    os.path.join(upload_dir, filename),
                )
            except Exception as exc:  # gambar gagal dibuat tidak boleh menggagalkan seed
                click.echo(f'      [!] gagal membuat gambar {name}: {exc}')
                continue
            product.image = filename
            click.echo(f'      [img] {name} -> {filename}')

    db.session.commit()
    click.echo('\nSeed toko selesai.')


PROMO_NOTE = 'DATA DEMO (seed-promo)'
PROMO_BUYER_PREFIX = 'pembeli.demo'
# (nama produk, persen diskon contoh)
PROMO_DISCOUNTS = [
    ('Kaos Kampus Classic', 25), ('Hoodie Merchku Hitam', 20), ('Stiker Pack Merchku', 30),
    ('Lanyard Custom Merchku', 15), ('Hoodie Oversize Senja', 18), ('Kaos Grafis Ruang Kreatif', 22),
    ('Jaket Coach Himpunan', 12), ('Pin Enamel Himpunan', 28), ('Kaos Dry-Fit Run Club', 20),
    ('Tote Bag Race Pack', 15), ('Mug Enamel Ruang Kreatif', 10), ('Topi Baseball Hitam', 25),
]
# (nama produk, target jumlah terjual)
PROMO_SALES = [
    ('Stiker Pack Merchku', 2140), ('Lanyard Custom Merchku', 1530), ('Kaos Kampus Classic', 1250),
    ('Pin Enamel Himpunan', 970), ('Hoodie Merchku Hitam', 860), ('Tote Bag Kanvas Hitam', 640),
    ('Kaos Dry-Fit Run Club', 530), ('Hoodie Oversize Senja', 420), ('Kaos Grafis Ruang Kreatif', 380),
    ('Mug Keramik Putih', 310), ('Topi Baseball Hitam', 275), ('Jaket Coach Himpunan', 215),
    ('Almet Kampus Edisi 2026', 190), ('Notebook Dot Grid Himpunan', 160),
]


@click.command('seed-promo')
@click.option('--force', is_flag=True, default=False, help='Jalankan di production (berbahaya).')
@click.option('--hapus', is_flag=True, default=False, help='Hapus semua data demo seed-promo.')
@with_appcontext
def seed_promo(force, hapus):
    """Data DEMO: harga coret (diskon) + riwayat penjualan agar label "terjual" terisi.

    Pesanan demo dibuat sungguhan di database (status selesai, catatan admin
    'DATA DEMO (seed-promo)') oleh akun pembeli demo yang tidak bisa login.
    Hanya untuk presentasi/pengembangan — jangan dipakai di toko sungguhan.
    """
    import random
    import secrets
    from datetime import timedelta

    from flask import current_app

    from app.katalog.models import Product, _utcnow
    from app.pesanan.models import Order, OrderItem

    env = current_app.config.get('ENV', 'dev') or os.getenv('FLASK_ENV', 'dev')
    if env in ('prod', 'production') and not force:
        raise click.ClickException(
            'seed-promo berisi data demo dan menolak berjalan di production.'
        )

    def discounted_price(price, percent):
        # Harga coret dibulatkan ke atas ke ribuan terdekat
        raw = price / (1 - percent / 100)
        return int(-(-raw // 1000) * 1000)

    if hapus:
        orders = Order.query.filter_by(admin_note=PROMO_NOTE).all()
        for order in orders:
            db.session.delete(order)
        db.session.flush()
        buyers = User.query.filter(User.email.like(f'{PROMO_BUYER_PREFIX}%@demo.test')).all()
        for buyer in buyers:
            if not Order.query.filter_by(user_id=buyer.id).first():
                db.session.delete(buyer)
        reset = 0
        for name, percent in PROMO_DISCOUNTS:
            product = Product.query.filter_by(name=name).first()
            if product and product.original_price == discounted_price(product.price, percent):
                product.original_price = None
                reset += 1
        db.session.commit()
        click.echo(f'Dihapus: {len(orders)} pesanan demo, {len(buyers)} pembeli demo, {reset} harga coret.')
        return

    # ── Harga coret ────────────────────────────────────────────────────────
    for name, percent in PROMO_DISCOUNTS:
        product = Product.query.filter_by(name=name).first()
        if not product:
            click.echo(f'  [!] produk tidak ditemukan: {name}')
            continue
        if product.original_price:
            click.echo(f'  [=] sudah punya harga coret: {name}')
            continue
        product.original_price = discounted_price(product.price, percent)
        click.echo(f'  [+] diskon {percent}%: {name}')

    # ── Pembeli demo (tidak aktif → tidak bisa login) ─────────────────────
    cities = [
        ('Bandung', 'Jawa Barat', '40132'), ('Jakarta Selatan', 'DKI Jakarta', '12430'),
        ('Batam', 'Kepulauan Riau', '29461'), ('Surabaya', 'Jawa Timur', '60111'),
        ('Yogyakarta', 'DI Yogyakarta', '55281'), ('Medan', 'Sumatera Utara', '20112'),
    ]
    buyers = []
    for index in range(1, 41):
        email = f'{PROMO_BUYER_PREFIX}{index}@demo.test'
        buyer = User.query.filter_by(email=email).first()
        if not buyer:
            city, province, postal = cities[index % len(cities)]
            buyer = User(
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(24)),
                role='customer',
                is_active=False,
                recipient_name=f'Pembeli Demo {index}',
                address=f'Jl. Contoh No. {index}',
                city=city, province=province, postal_code=postal,
                phone=f'0812000000{index:02d}',
            )
            db.session.add(buyer)
        buyers.append(buyer)
    db.session.flush()

    # ── Riwayat penjualan ─────────────────────────────────────────────────
    rng = random.Random(2026)
    now = _utcnow()
    created_orders = 0
    for name, target in PROMO_SALES:
        product = Product.query.filter_by(name=name).first()
        if not product:
            click.echo(f'  [!] produk tidak ditemukan: {name}')
            continue
        already = (
            db.session.query(db.func.coalesce(db.func.sum(OrderItem.quantity), 0))
            .join(Order, Order.id == OrderItem.order_id)
            .filter(OrderItem.product_id == product.id, Order.admin_note == PROMO_NOTE)
            .scalar()
        ) or 0
        remaining = target - int(already)
        while remaining > 0:
            # Pesanan komunitas/organisasi biasanya borongan
            quantity = min(remaining, rng.choice([1, 2, 3, 5, 10, 12, 20, 25, 30, 50]))
            buyer = rng.choice(buyers)
            created = now - timedelta(days=rng.randint(1, 150), hours=rng.randint(0, 23))
            order = Order(
                user_id=buyer.id, status='selesai',
                recipient_name=buyer.recipient_name, address=buyer.address,
                city=buyer.city, province=buyer.province, postal_code=buyer.postal_code,
                phone=buyer.phone, payment_method='bank_transfer',
                total_price=product.price * quantity,
                admin_note=PROMO_NOTE, created_at=created, updated_at=created,
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(OrderItem(
                order_id=order.id, product_id=product.id, product_name=product.name,
                product_description=product.description, product_type=product.product_type,
                product_color=product.color,
                size=rng.choice(['M', 'L', 'XL']) if product.use_sizes else None,
                quantity=quantity, unit_price=product.price,
            ))
            remaining -= quantity
            created_orders += 1
        click.echo(f'  [+] {name}: {target} terjual')

    db.session.commit()
    click.echo(f'\nSeed promo selesai ({created_orders} pesanan demo baru).')
    click.echo('Hapus lagi kapan saja: flask seed-promo --hapus')


def _make_demo_order(user, items, status):
    """Buat satu pesanan demo jika belum ada (cek berdasarkan user + status + jumlah item)."""
    from app.pesanan.models import Order, OrderItem

    # Cek kasar: kalau user sudah punya order dengan status ini, skip
    existing = Order.query.filter_by(user_id=user.id, status=status).first()
    if existing:
        for order_item in existing.items:
            product = order_item.product
            if product:
                order_item.product_description = (
                    order_item.product_description or product.description
                )
                order_item.product_type = order_item.product_type or product.product_type
                order_item.product_color = order_item.product_color or product.color
        if existing.recipient_name.startswith('Demo '):
            existing.recipient_name = user.recipient_name or existing.recipient_name
            existing.address = user.address or existing.address
            existing.address_label = user.address_label or 'rumah'
            existing.district = user.district or existing.district
            existing.city = user.city or existing.city
            existing.postal_code = user.postal_code or existing.postal_code
            existing.province = user.province or existing.province
            existing.phone = user.phone or existing.phone
        click.echo(f'  [=] pesanan sudah ada: user={user.email} status={status}')
        return

    total = sum(p.price * qty for p, _, qty in items)
    order = Order(
        user_id=user.id,
        status=status,
        recipient_name=user.recipient_name or f'Demo {user.email.split("@")[0].title()}',
        address=user.address or 'Jl. Demo Merdeka No. 11',
        address_label=user.address_label or 'rumah',
        district=user.district or 'Coblong',
        city=user.city or 'Bandung',
        postal_code=user.postal_code or '40132',
        province=user.province or 'Jawa Barat',
        phone=user.phone or '081234567890',
        total_price=total,
    )
    db.session.add(order)
    db.session.flush()

    for product, size, qty in items:
        db.session.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            product_description=product.description,
            product_type=product.product_type,
            product_color=product.color,
            size=size,
            quantity=qty,
            unit_price=product.price,
        ))

    click.echo(f'  [+] pesanan: user={user.email} status={status} total=Rp{total:,}')


# Nama/warna produk disesuaikan dengan fotonya: nama lama -> (nama baru, jenis, warna).
# Jenis/warna None = biarkan nilai yang ada.
PRODUCT_FIXES = {
    'Kaos Reg': ('Kaos Polos Putih', 'Kaos regular fit', 'Putih'),
    'Hoodie Merchku Navy': ('Hoodie Merchku Hitam', 'Hoodie fleece', 'Hitam'),
    'Jaket Varsity Premium': ('Jaket Harrington Krem', 'Jaket harrington', 'Krem'),
    'Tote Bag Kanvas Merchku': ('Tote Bag Kanvas Hitam', 'Tote bag kanvas', 'Hitam'),
    'Lanyard Custom Merchku': ('Lanyard Custom Merchku', 'Lanyard', 'Krem'),
    'Topi Baseball Merchku': ('Topi Baseball Hitam', 'Topi baseball', 'Hitam'),
    'Lanyard Polos': ('Lanyard Polos Krem', 'Lanyard', 'Krem'),
    'Lanyard Custom': ('Lanyard Custom Krem', 'Lanyard', 'Krem'),
    'Tote Bag Canvas': ('Tote Bag Kanvas Hijau Army', 'Tote bag kanvas', 'Hijau army'),
    'Tote Bag Print': ('Tote Bag Kanvas Putih', 'Tote bag kanvas', 'Putih'),
    'Pin Badge Set': ('Pin Bulat Putih', 'Pin', 'Putih'),
    'Notebook A5': ('Notebook A5 Krem', 'Notebook A5', 'Krem'),
    'Mug Kampus': ('Mug Keramik Putih', 'Mug keramik', 'Putih'),
    'Gantungan Kunci': ('Gantungan Kunci Akrilik', 'Gantungan kunci akrilik', 'Bening'),
    'Almet Kampus 2026': ('Almet Kampus Merah 2026', 'Jas almamater', 'Merah'),
    'Kaos Komunitas': ('Kaos Komunitas Navy', 'Kaos regular fit', 'Navy'),
    'Hoodie Polos': ('Hoodie Polos Krem', 'Hoodie pullover', 'Krem'),
    'Hoodie Printing': ('Hoodie Polos Navy', 'Hoodie fleece', 'Navy'),
    'Jaket Varsity': ('Jaket Bomber Navy', 'Jaket bomber', 'Navy'),
    'Jaket Bomber': ('Jaket Harrington Putih', 'Jaket harrington', 'Putih'),
    'Hoodie Oversize Senja': ('Hoodie Oversize Senja', None, 'Peach'),
    'Kaos Grafis Ruang Kreatif': ('Kaos Grafis Ruang Kreatif', None, 'Cokelat'),
    'Tote Bag Ruang Kreatif': ('Tote Bag Ruang Kreatif', None, 'Cokelat'),
    'Topi Dad Hat Senja': ('Topi Dad Hat Senja', None, 'Krem'),
    'Mug Enamel Ruang Kreatif': ('Mug Enamel Ruang Kreatif', None, 'Krem'),
    'Kaos Dry-Fit Run Club': ('Kaos Dry-Fit Run Club', None, 'Navy ungu'),
    'Hoodie Run Club Night': ('Hoodie Run Club Night', None, 'Navy ungu'),
    'Topi Running Run Club': ('Topi Running Run Club', None, 'Putih'),
    'Gantungan Kunci Medali': ('Gantungan Kunci Medali', None, 'Hitam'),
    'Tote Bag Race Pack': ('Tote Bag Race Pack', None, 'Putih'),
}


@click.command('sesuaikan-produk')
@with_appcontext
def sesuaikan_produk():
    """Samakan nama, jenis, dan warna produk demo dengan foto produknya (idempoten)."""
    from app.katalog.models import Product

    changed = 0
    for old_name, (new_name, product_type, color) in PRODUCT_FIXES.items():
        product = Product.query.filter_by(name=old_name).first()
        if not product:
            continue
        if new_name != old_name:
            if Product.query.filter_by(name=new_name).first():
                click.echo(f'  [!] lewati {old_name}: nama {new_name} sudah dipakai')
                continue
            product.name = new_name
            if product.description and product.description.startswith(f'{old_name}.'):
                product.description = new_name + product.description[len(old_name):]
        if product_type:
            product.product_type = product_type
        if color:
            product.color = color
        changed += 1
        click.echo(f'  [~] {old_name} -> {new_name} ({color or "-"})')

    # Riwayat pesanan menyimpan nama produk saat dibeli. Khusus pesanan akun demo
    # (@demo.test) ikut disamakan agar data demo tidak tampak janggal; pesanan
    # pembeli sungguhan dibiarkan sesuai aslinya.
    from app.pesanan.models import Order, OrderItem

    demo_orders = (
        db.session.query(Order.id).join(User, User.id == Order.user_id)
        .filter(User.email.like('%@demo.test'))
    )
    snapshots = 0
    for old_name, (new_name, product_type, color) in PRODUCT_FIXES.items():
        product = Product.query.filter_by(name=new_name).first()
        if not product:
            continue
        items = OrderItem.query.filter(
            OrderItem.product_id == product.id,
            OrderItem.product_name.in_({old_name, new_name}),
            OrderItem.order_id.in_(demo_orders),
        ).all()
        for item in items:
            if (item.product_name, item.product_color) == (new_name, color or item.product_color):
                continue
            item.product_name = new_name
            item.product_description = product.description
            item.product_type = product_type or item.product_type
            item.product_color = color or item.product_color
            snapshots += 1
    db.session.commit()
    click.echo(f'\nSelesai, {changed} produk disesuaikan, {snapshots} item pesanan demo diperbarui.')


SOCIAL_NOTE_PREFIX = 'pengikut.demo'
SOCIAL_FIRST_NAMES = [
    'Rizky', 'Nadia', 'Fajar', 'Ayu', 'Dimas', 'Salsa', 'Bagas', 'Citra', 'Yoga', 'Putri',
    'Raka', 'Intan', 'Arif', 'Dewi', 'Bima', 'Nabila', 'Galih', 'Tasya', 'Reza', 'Aulia',
    'Hafiz', 'Melati', 'Iqbal', 'Sinta', 'Farhan', 'Laras', 'Kevin', 'Anisa', 'Andre', 'Zahra',
    'Wahyu', 'Rina', 'Ilham', 'Vina', 'Gilang', 'Mega', 'Rafi', 'Siska', 'Taufik', 'Dinda',
]
SOCIAL_LAST_NAMES = [
    'Pratama', 'Saputra', 'Lestari', 'Nugroho', 'Wulandari', 'Hidayat', 'Permata', 'Kusuma',
    'Ramadhan', 'Siregar', 'Hasibuan', 'Maharani', 'Setiawan', 'Anggraini', 'Firmansyah', 'Utami',
]
# Komentar ulasan demo per kategori: (rating, komentar)
SOCIAL_REVIEWS = {
    'pakaian': [
        (5, 'Bahannya adem dan jahitannya rapi banget. Ukuran sesuai size chart, mantap!'),
        (5, 'Warnanya sama persis kayak di foto. Dipakai ke kampus banyak yang nanya beli di mana 😁'),
        (5, 'Pengiriman cepat, packing rapi pakai plastik tebal. Recommended seller!'),
        (4, 'Kualitas oke untuk harganya, cuma agak kebesaran sedikit. Next order ambil size di bawahnya.'),
        (5, 'Sablonnya tajam dan nggak luntur setelah dicuci. Puas banget kak.'),
        (5, 'Udah kedua kalinya order di sini, kualitasnya konsisten. Makasih kak!'),
        (4, 'Bagus, nyaman dipakai seharian. Pengiriman sehari lebih lama dari estimasi.'),
        (5, 'Bahannya tebal tapi nggak panas. Cocok buat kegiatan himpunan.'),
        (3, 'Barang sesuai, tapi warnanya sedikit lebih gelap dari foto.'),
        (5, 'Order borongan buat angkatan, semua ukuran pas dan datang tepat waktu 🙏'),
        (5, 'Penjual ramah dan fast response pas ditanya ukuran.'),
        (4, 'Overall puas, jahitan kuat. Semoga ada pilihan warna lain.'),
    ],
    'aksesori': [
        (5, 'Lucu banget, kualitas cetaknya bagus dan warnanya cerah.'),
        (5, 'Sesuai deskripsi, packing aman. Langsung dipakai hari itu juga.'),
        (4, 'Bagus, cuma ukurannya sedikit lebih kecil dari bayangan saya.'),
        (5, 'Murah tapi nggak murahan. Bakal repeat order buat teman-teman.'),
        (5, 'Pengiriman kilat! Barang mulus tanpa cacat.'),
        (5, 'Cocok buat hadiah wisuda teman, dia suka banget 😍'),
        (4, 'Kualitas oke, bahan kokoh. Pengiriman agak lama karena antre kurir.'),
        (5, 'Detailnya rapi, logo jelas. Seller responsif.'),
        (3, 'Lumayan, tapi warna aslinya agak beda sedikit dari foto.'),
        (5, 'Mantap, sesuai ekspektasi. Terima kasih kak!'),
    ],
}
SOCIAL_SELLER_REPLIES = [
    'Terima kasih banyak kak sudah belanja di toko kami 🙏 Ditunggu order berikutnya ya!',
    'Makasih reviewnya kak, senang produknya cocok 😊',
    'Terima kasih masukannya kak, akan kami tingkatkan lagi ya 🙏',
]
# Target jumlah pengikut per toko (email penjual)
SOCIAL_FOLLOWERS = {
    'seller@demo.test': 486,
    'ruangkreatif@demo.test': 312,
    'himpunanstore@demo.test': 228,
    'runclub@demo.test': 164,
}
SOCIAL_ACCOUNTS = max(SOCIAL_FOLLOWERS.values())


@click.command('seed-sosial')
@click.option('--force', is_flag=True, default=False, help='Jalankan di production (berbahaya).')
@click.option('--hapus', is_flag=True, default=False, help='Hapus semua ulasan & pengikut demo.')
@with_appcontext
def seed_sosial(force, hapus):
    """Data DEMO: ulasan produk + pengikut toko dari akun demo yang tidak bisa login.

    Semua data dibuat oleh akun 'pengikut.demo{n}@demo.test' (nonaktif), jadi
    mudah dihapus lagi dengan --hapus. Hanya untuk presentasi/pengembangan.
    """
    import random
    import secrets
    from datetime import timedelta

    from flask import current_app

    from app.katalog.follow_model import ShopFollow
    from app.katalog.models import Product, _utcnow
    from app.katalog.review_model import Review

    env = current_app.config.get('ENV', 'dev') or os.getenv('FLASK_ENV', 'dev')
    if env in ('prod', 'production') and not force:
        raise click.ClickException('seed-sosial berisi data demo dan menolak berjalan di production.')

    demo_users = User.query.filter(User.email.like(f'{SOCIAL_NOTE_PREFIX}%@demo.test'))
    if hapus:
        ids = [u.id for u in demo_users.all()]
        reviews = Review.query.filter(Review.user_id.in_(ids)).delete(synchronize_session=False) if ids else 0
        follows = ShopFollow.query.filter(ShopFollow.follower_id.in_(ids)).delete(synchronize_session=False) if ids else 0
        users = demo_users.delete(synchronize_session=False)
        db.session.commit()
        click.echo(f'Dihapus: {reviews} ulasan, {follows} pengikut, {users} akun demo.')
        return

    rng = random.Random(2610)
    now = _utcnow()
    # Satu hash untuk semua akun demo: akun nonaktif, password acak tidak pernah dipakai.
    unusable_hash = hash_password(secrets.token_urlsafe(24))
    existing = {u.email: u for u in demo_users.all()}
    accounts = []
    for index in range(1, SOCIAL_ACCOUNTS + 1):
        email = f'{SOCIAL_NOTE_PREFIX}{index}@demo.test'
        user = existing.get(email)
        if not user:
            first = SOCIAL_FIRST_NAMES[(index - 1) % len(SOCIAL_FIRST_NAMES)]
            last = SOCIAL_LAST_NAMES[((index - 1) // len(SOCIAL_FIRST_NAMES) + index) % len(SOCIAL_LAST_NAMES)]
            user = User(
                email=email, password_hash=unusable_hash, role='customer', is_active=False,
                recipient_name=f'{first} {last}',
                created_at=now - timedelta(days=rng.randint(30, 400)),
            )
            db.session.add(user)
        accounts.append(user)
    db.session.flush()
    click.echo(f'  [+] {len(accounts)} akun demo siap')

    # ── Pengikut toko ─────────────────────────────────────────────────────
    for seller_email, target in SOCIAL_FOLLOWERS.items():
        seller = User.query.filter_by(email=seller_email).first()
        if not seller:
            click.echo(f'  [!] toko tidak ditemukan: {seller_email}')
            continue
        followed = {
            fid for (fid,) in db.session.query(ShopFollow.follower_id).filter_by(seller_id=seller.id)
        }
        added = 0
        for user in rng.sample(accounts, min(target, len(accounts))):
            if user.id in followed:
                continue
            db.session.add(ShopFollow(
                seller_id=seller.id, follower_id=user.id,
                created_at=now - timedelta(days=rng.randint(1, 200)),
            ))
            added += 1
        click.echo(f'  [+] {seller.shop_name}: +{added} pengikut')

    # ── Ulasan produk ─────────────────────────────────────────────────────
    total_reviews = 0
    for product in Product.query.filter_by(is_active=True).order_by(Product.id).all():
        pool = SOCIAL_REVIEWS['pakaian' if product.category in ('kaos', 'hoodie', 'jaket', 'almet') else 'aksesori']
        reviewed = {uid for (uid,) in db.session.query(Review.user_id).filter_by(product_id=product.id)}
        want = rng.randint(6, 18)
        candidates = [u for u in rng.sample(accounts, min(60, len(accounts))) if u.id not in reviewed]
        for user in candidates[:max(0, want - len(reviewed))]:
            rating, comment = rng.choice(pool)
            created = now - timedelta(days=rng.randint(1, 120), hours=rng.randint(0, 23))
            review = Review(product_id=product.id, user_id=user.id, rating=rating,
                            comment=comment, created_at=created)
            if rng.random() < 0.3:
                review.seller_reply = rng.choice(SOCIAL_SELLER_REPLIES)
                review.replied_at = created + timedelta(hours=rng.randint(1, 30))
            db.session.add(review)
            total_reviews += 1

    db.session.commit()
    click.echo(f'\nSeed sosial selesai ({total_reviews} ulasan demo baru).')
    click.echo('Hapus lagi kapan saja: flask seed-sosial --hapus')
