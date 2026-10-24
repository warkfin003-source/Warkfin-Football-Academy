"""Environment-based configuration. Production starts locked; secrets belong in hosting settings."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .database import postgres_from_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get('DJANGO_DEBUG') == '1'
# Production remains closed until email delivery and owner setup pass release checks.
OWNER_SETUP_ENABLED = os.environ.get('OWNER_SETUP_ENABLED', '0') == '1'
OWNER_MFA_REQUIRED = True
OTP_TOTP_ISSUER = 'Warkfin Football Academy'
OWNER_MFA_MAX_AGE = 7200
OWNER_MFA_SETUP_MAX_AGE = 600
OWNER_ACTIVATION_ENABLED = os.environ.get('OWNER_ACTIVATION_ENABLED', '0') == '1'
PORTAL_ENABLED = os.environ.get('PORTAL_ENABLED', '1' if DEBUG else '0') == '1'
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured('Set DJANGO_SECRET_KEY before starting the backend.')
    SECRET_KEY = 'local-development-only-not-for-deployment-' * 2
ALLOWED_HOSTS = os.environ.get('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
# Django provides authentication, sessions, CSRF and admin; academy holds domain workflows.
INSTALLED_APPS = ['django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles', 'django_otp', 'django_otp.plugins.otp_totp', 'academy']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'whitenoise.middleware.WhiteNoiseMiddleware', 'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.common.CommonMiddleware', 'django.middleware.csrf.CsrfViewMiddleware', 'django.contrib.auth.middleware.AuthenticationMiddleware', 'django_otp.middleware.OTPMiddleware', 'django.contrib.messages.middleware.MessageMiddleware', 'django.middleware.clickjacking.XFrameOptionsMiddleware', 'academy.middleware.LaunchGateMiddleware', 'academy.middleware.PortalMiddleware', 'academy.mfa.OwnerMFAMiddleware']
ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'DIRS': [BASE_DIR / 'templates'], 'APP_DIRS': True, 'OPTIONS': {'context_processors': ['django.template.context_processors.request', 'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
# Web requests use the pooled URL; migration_settings selects the direct endpoint separately.
if os.environ.get('DATABASE_URL'):
    DATABASES = {'default': postgres_from_url(os.environ['DATABASE_URL'])}
elif os.environ.get('POSTGRES_HOST'):
    DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': os.environ['POSTGRES_DB'], 'USER': os.environ['POSTGRES_USER'], 'PASSWORD': os.environ['POSTGRES_PASSWORD'], 'HOST': os.environ['POSTGRES_HOST'], 'PORT': os.environ.get('POSTGRES_PORT', '5432'), 'OPTIONS': {'sslmode': os.environ.get('POSTGRES_SSLMODE', 'require')}, 'CONN_MAX_AGE': 60}}
else:
    if not DEBUG:
        raise ImproperlyConfigured('Production requires PostgreSQL configuration.')
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
AUTH_USER_MODEL = 'academy.User'
# Apply password rules to both initial signup and password-setting forms.
AUTH_PASSWORD_VALIDATORS = [{'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'}, {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 12}}, {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'}, {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'}]
LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Africa/Lagos'
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
# WhiteNoise serves versioned static assets without a separate paid storage service.
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'}, 'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'}}
# Production uses a real transport. Local development uses console output only.
EMAIL_TRANSPORT = os.environ.get('EMAIL_TRANSPORT', 'smtp')
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend' if DEBUG else ('academy.email_backend.BrevoEmailBackend' if EMAIL_TRANSPORT == 'brevo' else 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = True
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'academy@localhost')
PORTAL_ORIGIN = os.environ.get('PORTAL_ORIGIN', 'http://127.0.0.1:8000').rstrip('/')
EMAIL_READY = bool(BREVO_API_KEY) if EMAIL_TRANSPORT == 'brevo' else bool(EMAIL_HOST)
if not DEBUG and (PORTAL_ENABLED or OWNER_ACTIVATION_ENABLED) and (not EMAIL_READY or not PORTAL_ORIGIN.startswith('https://') or DEFAULT_FROM_EMAIL.endswith('@localhost')):
    raise ImproperlyConfigured('Configure HTTPS PORTAL_ORIGIN and a real email sender/service.')
# Restrict state-changing browser requests to the configured portal origin.
CSRF_TRUSTED_ORIGINS = [PORTAL_ORIGIN] if PORTAL_ORIGIN.startswith('https://') else []
# Keep authenticated sessions private and require HTTPS outside local development.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_AGE = 7200
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
# Enable ONLY behind a proxy that strips incoming X-Forwarded-Proto.
if os.environ.get('TRUST_HTTPS_PROXY') == '1':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
DATA_UPLOAD_MAX_MEMORY_SIZE = 262144
PASSWORD_RESET_TIMEOUT = 3600
OWNER_LOGIN_EMAIL = os.environ.get('OWNER_LOGIN_EMAIL', '').strip().lower()

# Owner SMS destination is server-controlled; login forms cannot change it.
OWNER_MFA_METHOD = os.environ.get('OWNER_MFA_METHOD', 'totp')
OWNER_SMS_PHONE = os.environ.get('OWNER_SMS_PHONE', '').strip()
OWNER_SMS_SENDER = os.environ.get('OWNER_SMS_SENDER', 'Warkfin')

# Keep collections closed until merchant approval, sandbox tests and terms are complete.
PALMPAY_ENABLED = os.getenv('PALMPAY_ENABLED', '0') == '1'
PALMPAY_APP_ID = os.getenv('PALMPAY_APP_ID', '')
PALMPAY_PRIVATE_KEY = os.getenv('PALMPAY_PRIVATE_KEY', '')
PALMPAY_PUBLIC_KEY = os.getenv('PALMPAY_PUBLIC_KEY', '')
PALMPAY_BASE_URL = os.getenv('PALMPAY_BASE_URL', 'https://open-gw-sandbox.palmpay-inc.com')
PALMPAY_CHECKOUT_HOSTS = os.getenv('PALMPAY_CHECKOUT_HOSTS', '').split(',')
PAYMENT_TERMS = os.getenv('PAYMENT_TERMS', '')
