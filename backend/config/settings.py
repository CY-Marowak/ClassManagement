import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("CM_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("CM_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set CM_SECRET_KEY, or CM_DEBUG=1 for local development.")
    SECRET_KEY = "local-development-only-do-not-use-in-production-cm"
ALLOWED_HOSTS = os.environ.get("CM_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
FRONTEND_URL = os.environ.get("CM_FRONTEND_URL", "http://127.0.0.1:5173").rstrip("/")
if not DEBUG and not FRONTEND_URL.startswith("https://"):
    raise RuntimeError("Production CM_FRONTEND_URL must use HTTPS.")
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "rest_framework",
    "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "cm"),
        "USER": os.environ.get("PGUSER", "cm"),
        "PASSWORD": os.environ.get("PGPASSWORD", "cm-local-only" if DEBUG else ""),
        "HOST": os.environ.get("PGHOST", "127.0.0.1"),
        "PORT": os.environ.get("PGPORT", "55432"),
    }
}
AUTH_USER_MODEL = "core.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.IsReadyUser"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = [FRONTEND_URL]
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "no-referrer"
EMAIL_BACKEND = os.environ.get(
    "CM_EMAIL_BACKEND",
    "django.core.mail.backends.filebased.EmailBackend"
    if DEBUG
    else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_FILE_PATH = BASE_DIR.parent / ".local" / "mail"
EMAIL_HOST = os.environ.get("CM_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("CM_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("CM_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("CM_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("CM_EMAIL_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = os.environ.get("CM_FROM_EMAIL", "CM <noreply@example.com>")
LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
