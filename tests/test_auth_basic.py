from app import db
from app.auth.models import User
from app.auth.security import hash_password
from tests.helpers import create_test_app


def test_register_and_login():
    app = create_test_app()
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
    app = create_test_app()
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


def test_login_normalizes_pasted_email():
    app = create_test_app()
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()
        db.session.add(User(
            email='known@merchku.test',
            password_hash=hash_password('Password12345'),
            role='customer',
            is_active=True,
        ))
        db.session.commit()

    with app.test_client() as c:
        response = c.post(
            '/auth/login',
            data={'email': '  KNOWN@MERCHKU.TEST ', 'password': 'Password12345'},
        )
        assert response.status_code == 302
        assert not response.headers['Location'].endswith('/auth/login')


def test_auth_pages_have_password_visibility_controls():
    app = create_test_app()

    with app.test_client() as c:
        login = c.get('/auth/login')
        register = c.get('/auth/register')

    assert login.status_code == 200
    assert b"data-password-toggle='password'" in login.data
    assert register.status_code == 200
    assert b"data-password-toggle='password'" in register.data
    assert b"data-password-toggle='password2'" in register.data


def test_form_auth_punya_validasi_client_side():
    app = create_test_app()
    with app.test_client() as c:
        login = c.get('/auth/login').data
        register = c.get('/auth/register').data

    for page in (login, register):
        assert b'data-validate' in page
        assert b'data-validate-email' in page
        assert b'form-validation.js' in page
    assert b'minlength="10"' in register
    assert b'data-match="password"' in register
