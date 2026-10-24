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
