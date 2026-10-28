from sqlalchemy.engine import URL

from config import _database_uri


def test_mysql_database_url_uses_pymysql_and_escapes_credentials(monkeypatch):
    monkeypatch.delenv('SQLALCHEMY_DATABASE_URI', raising=False)
    monkeypatch.setenv('DB_ENGINE', 'mysql')
    monkeypatch.setenv('DB_USER', 'merchku')
    monkeypatch.setenv('DB_PASSWORD', 'p@ss:/word')
    monkeypatch.setenv('DB_HOST', '127.0.0.1')
    monkeypatch.setenv('DB_PORT', '3307')
    monkeypatch.setenv('DB_NAME', 'merchku')

    uri = _database_uri()

    assert isinstance(uri, URL)
    assert uri.drivername == 'mysql+pymysql'
    assert uri.username == 'merchku'
    assert uri.password == 'p@ss:/word'
    assert uri.port == 3307
    assert uri.database == 'merchku'
    assert uri.query == {'charset': 'utf8mb4'}


def test_explicit_database_uri_takes_precedence(monkeypatch):
    monkeypatch.setenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///explicit-test.db')
    monkeypatch.setenv('DB_ENGINE', 'mysql')

    assert _database_uri() == 'sqlite:///explicit-test.db'


def _app_with_db_error(orig_args):
    from sqlalchemy.exc import OperationalError

    from tests.helpers import create_test_app

    app = create_test_app()

    @app.get('/_db_error')
    def _db_error():
        raise OperationalError('SELECT 1', {}, Exception(*orig_args))

    return app


def test_mysql_mati_menampilkan_petunjuk_503():
    app = _app_with_db_error((2003, "Can't connect to MySQL server"))
    response = app.test_client().get('/_db_error')

    assert response.status_code == 503
    assert b'Database MySQL belum menyala' in response.data


def test_error_database_lain_tidak_dianggap_mysql_mati():
    app = _app_with_db_error((1146, "Table 'merchku.x' doesn't exist"))
    app.testing = False
    response = app.test_client().get('/_db_error')

    assert response.status_code == 500
    assert b'Database MySQL belum menyala' not in response.data


def test_database_url_render_diarahkan_ke_psycopg(monkeypatch):
    monkeypatch.delenv('SQLALCHEMY_DATABASE_URI', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgres://u:p@db.render.com:5432/merchku')

    assert _database_uri() == 'postgresql+psycopg://u:p@db.render.com:5432/merchku'


def test_kunci_akun_demo_mengganti_password_akun_demo_aktif():
    from app import db
    from app.auth.models import User
    from app.auth.security import hash_password, verify_password
    from tests.helpers import create_test_app

    app = create_test_app()
    with app.app_context():
        User.query.delete()
        db.session.add_all([
            User(email='admin@demo.test', password_hash=hash_password('AdminDemo1234'), role='admin', is_active=True),
            User(email='nonaktif@demo.test', password_hash=hash_password('LamaSekali123'), role='customer', is_active=False),
            User(email='asli@kampus.ac.id', password_hash=hash_password('PunyaSendiri1'), role='customer', is_active=True),
        ])
        db.session.commit()

    result = app.test_cli_runner().invoke(args=['kunci-akun-demo', '--password', 'RahasiaBaru2026'])
    assert result.exit_code == 0, result.output

    with app.app_context():
        def pw(email, password):
            return verify_password(User.query.filter_by(email=email).first().password_hash, password)
        assert pw('admin@demo.test', 'RahasiaBaru2026')
        assert not pw('admin@demo.test', 'AdminDemo1234')
        assert pw('nonaktif@demo.test', 'LamaSekali123')
        assert pw('asli@kampus.ac.id', 'PunyaSendiri1')

    short = app.test_cli_runner().invoke(args=['kunci-akun-demo', '--password', 'pendek'])
    assert short.exit_code != 0


def test_proxy_fix_membaca_ip_asli_pengunjung():
    from flask import request

    from tests.helpers import create_test_app

    for x_for, expected in ((0, '127.0.0.1'), (1, '203.0.113.9')):
        app = create_test_app(PROXY_FIX_X_FOR=x_for)
        app.add_url_rule('/_ip', 'ip', lambda: request.remote_addr)
        response = app.test_client().get('/_ip', headers={'X-Forwarded-For': '203.0.113.9'})
        assert response.get_data(as_text=True) == expected
