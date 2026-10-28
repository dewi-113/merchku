"""Smoke test setelah deploy: jalankan dengan environment yang sama seperti server.

Dipakai CI (job PostgreSQL) setelah `scripts/render-start.sh` menjalankan migrasi
dan seed. Cek halaman utama terbuka, admin demo bisa login dengan DEMO_PASSWORD,
dan password bawaan seed (yang tertulis di repo) sudah tidak berlaku.

    python scripts/smoke_deploy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.katalog.models import Product


def main():
    app = create_app()
    app.config.update(WTF_CSRF_ENABLED=False, RATELIMIT_ENABLED=False)
    print('Database:', str(app.config['SQLALCHEMY_DATABASE_URI']).split('://')[0])

    with app.app_context():
        product = Product.query.filter_by(is_active=True).first()
        assert product, 'tidak ada produk aktif (seed gagal?)'
        product_id = product.id

    failures = []
    # Cookie sesi memakai flag Secure (SECURE_COOKIES=1), jadi uji lewat https
    client = app.test_client()
    client.environ_base['wsgi.url_scheme'] = 'https'

    def check(path, expected=200, contains=None):
        response = client.get(path, base_url='https://localhost')
        ok = response.status_code == expected and (contains is None or contains in response.data)
        print(f"{'OK ' if ok else 'GAGAL'} {response.status_code} {path}")
        if not ok:
            failures.append(path)
        return response

    check('/', contains=b'promo-banner')
    check('/katalog/')
    check('/katalog/?q=kaos&sort=termurah')
    check(f'/katalog/{product_id}')
    check('/auth/register')
    health = client.get('/healthz', base_url='https://localhost').get_json()
    print('healthz', health)
    if not health or not health.get('db'):
        failures.append('/healthz')

    def login(password):
        client.get('/auth/logout', base_url='https://localhost')
        client.post('/auth/login', base_url='https://localhost',
                    data={'email': 'admin@demo.test', 'password': password})
        return client.get('/admin/', base_url='https://localhost').status_code

    if login('AdminDemo1234') == 200:
        print('GAGAL password bawaan repo masih bisa dipakai')
        failures.append('kunci-akun-demo')
    else:
        print('OK  password bawaan repo ditolak')

    if login(os.environ['DEMO_PASSWORD']) == 200:
        print('OK  admin login dengan DEMO_PASSWORD')
        check('/admin/laporan')
        check('/admin/produk')
    else:
        print('GAGAL admin tidak bisa login dengan DEMO_PASSWORD')
        failures.append('/admin/')

    if failures:
        print('Smoke test gagal:', ', '.join(failures))
        sys.exit(1)
    print('Smoke test lulus.')


if __name__ == '__main__':
    main()
