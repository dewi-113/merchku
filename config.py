import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _abs(path: str) -> str:
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


class Config:
    APP_NAME = os.getenv('APP_NAME', 'merchku')
    ENV = os.getenv('ENV', 'dev')
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY and (os.getenv('ENV') == 'prod' or os.getenv('FLASK_ENV') == 'production'):
        # fail-closed: production wajib punya SECRET_KEY dari env
        raise RuntimeError('SECRET_KEY wajib di production (set lewat environment variable)')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///merchku.db')
    LOG_DIR = os.path.abspath(os.getenv('LOG_DIR', 'logs'))
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', '10485760'))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    TRUSTED_PROXIES = os.getenv('TRUSTED_PROXIES', '127.0.0.1/32,::1/128').split(',')
    SECURE_COOKIES = os.getenv('SECURE_COOKIES', '0') == '1'
    METRICS_TOKEN = os.getenv('METRICS_TOKEN', '')
    UPLOAD_PUBLIC = os.path.abspath(os.getenv('UPLOAD_PUBLIC', 'uploads/public'))
    UPLOAD_PRIVATE = os.path.abspath(os.getenv('UPLOAD_PRIVATE', 'uploads/private'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', '16777216'))  # 16MB


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False
    TESTING = False


config_map = {
    'dev': DevConfig,
    'prod': ProdConfig,
    'development': DevConfig,
    'production': ProdConfig,
}
