from app import create_app


def test_healthz():
    app = create_app('dev')
    with app.test_client() as c:
        r = c.get('/healthz')
        assert r.status_code == 200
