from app import config_map, create_app, db
from config import DevConfig


def create_test_app(**overrides):
    class TestConfig(DevConfig):
        TESTING = True
        WTF_CSRF_ENABLED = False
        RATELIMIT_ENABLED = False
        RATE_LIMIT_DEFAULT = '200 per minute'
        SQLALCHEMY_DATABASE_URI = 'sqlite://'

    for key, value in overrides.items():
        setattr(TestConfig, key, value)
    TestConfig.__name__ = f'TestConfig{len(config_map)}'
    config_map['tests'] = TestConfig
    app = create_app('tests')
    app.config.update(overrides)
    with app.app_context():
        db.create_all()
    return app
