from app import create_app, db
from app.auth.models import User
from app.auth.security import hash_password


def test_register_and_login():
    app = create_app('dev')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()

    with app.test_client() as c:
        r = c.post(
            '/auth/register',
            data={'email': 'u1@merchku.test', 'password': 'Password12345', 'password2': 'Password12345'},
            follow_redirects=True,
        )
        assert r.status_code == 200
        with app.app_context():
            assert User.query.filter_by(email='u1@merchku.test').first() is not None

        r = c.post(
            '/auth/login',
            data={'email': 'u1@merchku.test', 'password': 'Password12345'},
        )
        assert r.status_code == 302
        assert r.headers['Location'].endswith('/healthz') or '/auth/login' not in r.headers['Location']


def test_login_wrong_password_generic_message():
    app = create_app('dev')
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()
        db.session.add(User(
            email='known@merchku.test', password_hash=hash_password('Password12345'),
            role='customer', is_active=True,
        ))
        db.session.commit()

    with app.test_client() as c:
        known = c.post('/auth/login', data={'email': 'known@merchku.test', 'password': 'wrongpassword'})
        unknown = c.post('/auth/login', data={'email': 'nobody@merchku.test', 'password': 'wrongpassword'})
        assert b'Email atau password salah' in known.data
        assert b'Email atau password salah' in unknown.data
