from tests.helpers import create_test_app


def test_healthz():
    app = create_test_app()
    with app.test_client() as c:
        r = c.get('/healthz')
        assert r.status_code == 200
        assert b'status' in r.data
