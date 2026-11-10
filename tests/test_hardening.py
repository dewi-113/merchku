"""Pengerasan keamanan untuk server di belakang Cloudflare + nginx."""

from app.core.utils import get_client_ip
from tests.helpers import create_test_app

TRUSTED = ['127.0.0.1/32', '::1/128']


def _ip(app, remote, xff=None):
    headers = {'X-Forwarded-For': xff} if xff else {}
    with app.test_request_context('/', headers=headers, environ_base={'REMOTE_ADDR': remote}):
        return get_client_ip(TRUSTED)


def test_xff_palsu_di_kiri_tidak_dipercaya():
    app = create_test_app()
    # Penyerang mengirim "X-Forwarded-For: 1.2.3.4"; nginx menambahkan IP aslinya di kanan
    assert _ip(app, '127.0.0.1', '1.2.3.4, 198.51.100.7') == '198.51.100.7'


def test_xff_diabaikan_bila_bukan_dari_proxy_tepercaya():
    app = create_test_app()
    assert _ip(app, '198.51.100.7', '1.2.3.4') == '198.51.100.7'


def test_xff_entri_rusak_tidak_dipercaya():
    app = create_test_app()
    assert _ip(app, '127.0.0.1', '1.2.3.4, bukan-ip') == '127.0.0.1'


def test_cookie_aman_dan_hsts_saat_https():
    app = create_test_app(SECURE_COOKIES=True, SESSION_COOKIE_SECURE=True)
    resp = app.test_client().get('/healthz')
    assert 'max-age=' in resp.headers.get('Strict-Transport-Security', '')
    assert app.config['SESSION_COOKIE_HTTPONLY'] is True
    assert app.config['SESSION_COOKIE_SAMESITE'] == 'Lax'
    csp = resp.headers['Content-Security-Policy']
    assert "object-src 'none'" in csp and "frame-ancestors 'self'" in csp


def test_tanpa_https_tidak_ada_hsts():
    app = create_test_app(SECURE_COOKIES=False)
    assert 'Strict-Transport-Security' not in app.test_client().get('/healthz').headers


def test_login_dibatasi_per_ip_walau_xff_diganti():
    app = create_test_app(RATELIMIT_ENABLED=True, RATELIMIT_LOGIN='3 per minute')
    statuses = []
    with app.test_client() as c:
        for i in range(5):
            r = c.post(
                '/auth/login',
                data={'email': f'x{i}@contoh.test', 'password': 'salah123456'},
                headers={'X-Forwarded-For': f'10.0.0.{i}, 198.51.100.7'},
            )
            statuses.append(r.status_code)
    assert 429 in statuses, statuses


def test_limiter_memakai_ip_asli():
    app = create_test_app()
    app.add_url_rule('/_k', 'k', lambda: __import__('app').client_ip_key())
    r = app.test_client().get(
        '/_k', headers={'X-Forwarded-For': '1.2.3.4, 198.51.100.7'},
        environ_base={'REMOTE_ADDR': '127.0.0.1'},
    )
    assert r.get_data(as_text=True) == '198.51.100.7'
