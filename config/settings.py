import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.getenv('CLINIC_ENV') == 'production'
CLINIC_PROXY_KEY = os.getenv('CLINIC_PROXY_KEY', '')
if CLINIC_PROXY_KEY and len(CLINIC_PROXY_KEY) < 32:
    raise ImproperlyConfigured('CLINIC_PROXY_KEY must be at least 32 characters.')
DEBUG = not PRODUCTION
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if PRODUCTION:
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured('Set a random DJANGO_SECRET_KEY of at least 50 characters.')
else:
    if not SECRET_KEY:
        secret_file = BASE_DIR / '.local-secret'
        try:
            fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w') as f:
                f.write(secrets.token_urlsafe(64))
        SECRET_KEY = secret_file.read_text().strip()
ALLOWED_HOSTS = [x.strip() for x in os.getenv('DJANGO_ALLOWED_HOSTS', 'drgerami-md.ir,localhost,127.0.0.1').split(',') if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv('DJANGO_CSRF_TRUSTED_ORIGINS', 'https://drgerami-md.ir').split(',') if x.strip()]
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'clinic']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'clinic.middleware.PrivateResponsesMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[BASE_DIR/'templates'],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages','clinic.context.clinic_context']}}]
WSGI_APPLICATION = 'config.wsgi.application'
DATA_DIR = Path(os.getenv('CLINIC_DATA_DIR', str(BASE_DIR / '.data')))
DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
db_url = os.getenv('DATABASE_URL', '')
if db_url:
    db = urlparse(db_url)
    if db.scheme not in ('postgres', 'postgresql') or not db.hostname or not db.path.strip('/'):
        raise ImproperlyConfigured('DATABASE_URL must be a PostgreSQL connection URL.')
    query = parse_qs(db.query)
    options = {'sslmode': query.get('sslmode', ['verify-full'])[0]}
    if PRODUCTION and options['sslmode'] != 'verify-full':
        raise ImproperlyConfigured('Production database TLS must use sslmode=verify-full.')
    if options['sslmode'] == 'verify-full':
        options['sslrootcert'] = os.getenv('DB_SSLROOTCERT', '/etc/ssl/certs/ca-certificates.crt')
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':unquote(db.path[1:]),'USER':unquote(db.username or ''),'PASSWORD':unquote(db.password or ''),'HOST':db.hostname,'PORT':db.port or 5432,'CONN_MAX_AGE':60,'OPTIONS':options}}
else:
    if PRODUCTION:
        raise ImproperlyConfigured('DATABASE_URL is required in production.')
    DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':DATA_DIR/'db.sqlite3','OPTIONS':{'timeout':20}}}
AUTH_PASSWORD_VALIDATORS = [{'NAME':'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},{'NAME':'django.contrib.auth.password_validation.MinimumLengthValidator','OPTIONS':{'min_length':12}},{'NAME':'django.contrib.auth.password_validation.CommonPasswordValidator'},{'NAME':'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'fa-ir'
TIME_ZONE = 'Asia/Tehran'
USE_I18N = True
USE_TZ = True
STATIC_URL = '/dash/static/'
STATIC_ROOT = Path(os.getenv('CLINIC_STATIC_ROOT', str(BASE_DIR / 'staticfiles')))
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
MEDIA_ROOT = DATA_DIR / 'documents'
# Deliberately no public MEDIA_URL or URL pattern. Files only via authorized FileResponse.
FILE_UPLOAD_PERMISSIONS = 0o600
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o700
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100
LOGIN_URL = '/dash/login/'
SESSION_COOKIE_NAME = '__Host-gerami-clinic' if PRODUCTION else 'gerami_session'
SESSION_COOKIE_PATH = '/'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_NAME = 'gerami_csrf'
CSRF_COOKIE_PATH = '/'
CSRF_COOKIE_SECURE = PRODUCTION
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
if os.getenv('TRUST_HTTPS_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CLINIC_NAME = 'دکتر امیرهوشنگ گرامی'
CLINIC_SITE = 'https://drgerami-md.ir'
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID','')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET','')
GOOGLE_TOKEN_ENCRYPTION_KEY = os.getenv('GOOGLE_TOKEN_ENCRYPTION_KEY','')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI','https://drgerami-md.ir/dash/calendar/oauth/callback/')
GOOGLE_CALENDAR_ACCOUNT = os.getenv('GOOGLE_CALENDAR_ACCOUNT','dr.gerami.md@gmail.com').strip().casefold()

CSRF_FAILURE_VIEW = 'clinic.portal_api.csrf_failure'
PASSWORD_RESET_TIMEOUT = 900
