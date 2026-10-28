import os

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Muat variabel dari file .env di root project (kalau ada).
# Variabel yang sudah diset di environment/system TIDAK ditimpa,
# jadi konfigurasi server produksi selalu menang.
load_dotenv(os.path.join(BASE_DIR, '.env'), override=False)


def _abs(path: str) -> str:
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(BASE_DIR, path)


def _database_uri() -> str | URL:
    explicit_uri = os.getenv('SQLALCHEMY_DATABASE_URI', '').strip()
    if explicit_uri:
        return explicit_uri

    # Render/Heroku memberi DATABASE_URL berformat postgres://...; arahkan ke driver psycopg 3
    database_url = os.getenv('DATABASE_URL', '').strip()
    if database_url:
        for prefix in ('postgres://', 'postgresql://'):
            if database_url.startswith(prefix):
                return 'postgresql+psycopg://' + database_url[len(prefix):]
        return database_url

    if os.getenv('DB_ENGINE', 'sqlite').strip().lower() in {'mysql', 'mariadb'}:
        return URL.create(
            'mysql+pymysql',
            username=os.getenv('DB_USER', 'merchku'),
            password=os.getenv('DB_PASSWORD', ''),
            host=os.getenv('DB_HOST', '127.0.0.1'),
            port=int(os.getenv('DB_PORT', '3306')),
            database=os.getenv('DB_NAME', 'merchku'),
            query={'charset': 'utf8mb4'},
        )

    return 'sqlite:///merchku.db'


class Config:
    APP_NAME = os.getenv('APP_NAME', 'merchku')
    ENV = os.getenv('ENV', 'dev')
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY and (os.getenv('ENV') == 'prod' or os.getenv('FLASK_ENV') == 'production'):
        # fail-closed: production wajib punya SECRET_KEY dari env
        raise RuntimeError('SECRET_KEY wajib di production (set lewat environment variable)')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = _database_uri()
    # Cek koneksi sebelum dipakai: database cloud memutus koneksi yang lama menganggur
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True}
    LOG_DIR = _abs(os.getenv('LOG_DIR', 'logs'))
    LOG_MAX_BYTES = int(os.getenv('LOG_MAX_BYTES', '10485760'))
    LOG_BACKUP_COUNT = int(os.getenv('LOG_BACKUP_COUNT', '5'))
    TRUSTED_PROXIES = os.getenv('TRUSTED_PROXIES', '127.0.0.1/32,::1/128').split(',')
    SECURE_COOKIES = os.getenv('SECURE_COOKIES', '0') == '1'
    # Jumlah reverse proxy di depan app (Render/nginx = 1) agar IP asli pengunjung terbaca
    PROXY_FIX_X_FOR = int(os.getenv('PROXY_FIX_X_FOR', '0'))
    # Izinkan email domain .test (akun demo) walau ENV=prod — hanya untuk server demo
    ALLOW_TEST_EMAILS = os.getenv('ALLOW_TEST_EMAILS', '0') == '1'
    METRICS_TOKEN = os.getenv('METRICS_TOKEN', '')
    UPLOAD_PUBLIC = _abs(os.getenv('UPLOAD_PUBLIC', 'uploads/public'))
    PRODUCT_PHOTOS_DIR = _abs(os.getenv('PRODUCT_PHOTOS_DIR', 'product_photos'))
    UPLOAD_PRIVATE = _abs(os.getenv('UPLOAD_PRIVATE', 'uploads/private'))
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', '16777216'))  # 16MB
    # Batas default rate limit (fallback bila route tidak punya batas sendiri)
    RATE_LIMIT_DEFAULT = os.getenv('RATE_LIMIT_DEFAULT', '200 per minute')
    BITESHIP_API_KEY = os.getenv('BITESHIP_API_KEY', '')
    BITESHIP_BASE_URL = os.getenv('BITESHIP_BASE_URL', 'https://api.biteship.com')
    SHIPPING_ORIGIN_POSTAL_CODE = os.getenv('SHIPPING_ORIGIN_POSTAL_CODE', '')
    CHECKOUT_SERVICE_FEE_RP = int(os.getenv('CHECKOUT_SERVICE_FEE_RP', '0'))
    CHECKOUT_SHIPPING_DISCOUNT_RP = int(os.getenv('CHECKOUT_SHIPPING_DISCOUNT_RP', '0'))
    FRAGILE_PACKING_FEE_RP = int(os.getenv('FRAGILE_PACKING_FEE_RP', '0'))
    MIDTRANS_SERVER_KEY = os.getenv('MIDTRANS_SERVER_KEY', '')
    MIDTRANS_CLIENT_KEY = os.getenv('MIDTRANS_CLIENT_KEY', '')
    MIDTRANS_IS_PRODUCTION = os.getenv('MIDTRANS_IS_PRODUCTION', '0') == '1'
    # Customer Service AI (opsional): aktif bila ANTHROPIC_API_KEY diisi
    CS_AI_MODEL = os.getenv('CS_AI_MODEL', 'claude-haiku-5-5')


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
