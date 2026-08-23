import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Configuração base da aplicação"""

    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError(
            "ERRO CRITICO: SECRET_KEY nao configurada. "
            "Configure no arquivo .env."
        )

    # Banco de dados — caminho unico em instance/
    db_path = os.path.join(basedir, 'instance', 'petshop.db')
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + db_path
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload de arquivos
    UPLOAD_FOLDER = os.path.join('static', 'uploads')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5MB

    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    TESTING = False

    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME')
    ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH')

    if not ADMIN_USERNAME or not ADMIN_PASSWORD_HASH:
        raise ValueError(
            "ERRO CRITICO: ADMIN_USERNAME ou ADMIN_PASSWORD_HASH nao configuradas."
        )

    # Sessao
    PERMANENT_SESSION_LIFETIME = 3600
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'

    # CSRF
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600

    # Rate limiting
    RATELIMIT_STORAGE_URL = os.environ.get('RATELIMIT_STORAGE_URL', 'memory://')

    RATELIMIT_DEFAULT = "200 per day;50 per hour"
    RATELIMIT_HEADERS_ENABLED = True

    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    ITEMS_PER_PAGE = 10

    # Cloudflare Turnstile (CAPTCHA dos formularios publicos)
    TURNSTILE_SITE_KEY = os.environ.get('TURNSTILE_SITE_KEY', '')
    TURNSTILE_SECRET_KEY = os.environ.get('TURNSTILE_SECRET_KEY', '')

    # Backup no Google Drive (Service Account) — ver README.md
    GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get('GOOGLE_SERVICE_ACCOUNT_FILE', '')
    GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID', '')


class DevelopmentConfig(Config):
    DEBUG = True
    TESTING = False
    SESSION_COOKIE_SECURE = False


class TestingConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    SESSION_COOKIE_SECURE = False
    WTF_CSRF_ENABLED = False
    # Testes automatizados não têm como resolver um captcha real do Cloudflare.
    TURNSTILE_SITE_KEY = '1x00000000000000000000AA'  # chave de teste sempre-passa da Cloudflare
    TURNSTILE_SECRET_KEY = '1x0000000000000000000000000000000AA'


class ProductionConfig(Config):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
