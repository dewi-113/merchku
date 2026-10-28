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
