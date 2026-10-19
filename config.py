import os


class Config:
    APP_NAME = os.getenv('APP_NAME','merchku')
    ENV = os.getenv('ENV','dev')
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        # fail-closed di prod
        if os.getenv('ENV') == 'prod' or os.getenv('FLASK_ENV') == 'production':
            raise RuntimeError('SECRET_KEY wajib')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI','sqlite:///merchku.db')
    LOG_DIR = os.getenv('LOG_DIR','logs')
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES','10485760'))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT','5'))
    TRUSTED_PROXIES = os.getenv('TRUSTED_PROXIES','127.0.0.1/32,::1/128').split(',')
    SECURE_COOKIES = os.getenv('SECURE_COOKIES','0') == '1'
    METRICS_TOKEN = os.getenv('METRICS_TOKEN','')
    UPLOAD_PUBLIC = os.getenv('UPLOAD_PUBLIC','uploads/public')
    UPLOAD_PRIVATE = os.getenv('UPLOAD_PRIVATE','uploads/private')
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH','16777216')) # 16MB

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
