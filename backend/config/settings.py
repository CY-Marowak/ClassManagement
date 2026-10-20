import os
from pathlib import Path
from typing import Any

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("CM_DEBUG", "0") == "1"
ALLOW_DEMO_DATA = os.environ.get("CM_ALLOW_DEMO_DATA", "0") == "1"
SECRET_KEY = os.environ.get("CM_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("Set CM_SECRET_KEY, or CM_DEBUG=1 for local development.")
    SECRET_KEY = "local-development-only-do-not-use-in-production-cm"
RENDER_HOST = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "")
ALLOWED_HOSTS = os.environ.get("CM_ALLOWED_HOSTS", RENDER_HOST or "127.0.0.1,localhost").split(",")
FRONTEND_URL = os.environ.get(
    "CM_FRONTEND_URL", f"https://{RENDER_HOST}" if RENDER_HOST else "http://127.0.0.1:5173"
).rstrip("/")
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
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
# Vite owns asset fingerprinting. Serve only its built public directory.
WHITENOISE_ROOT = BASE_DIR.parent / "frontend" / "dist"
WHITENOISE_INDEX_FILE = True
WHITENOISE_MAX_AGE = 0  # HTML must not point at assets from an older deployment.
DATABASES: dict[str, Any] = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PGDATABASE", "cm"),
        "USER": os.environ.get("PGUSER", "cm"),
        "PASSWORD": os.environ.get("PGPASSWORD", "cm-local-only" if DEBUG else ""),
        "HOST": os.environ.get("PGHOST", "127.0.0.1"),
        "PORT": os.environ.get("PGPORT", "55432"),
    }
}
if os.environ.get("DATABASE_URL"):
    try:
        DATABASES["default"] = dj_database_url.parse(
            os.environ["DATABASE_URL"], conn_max_age=0, ssl_require=not DEBUG
        )
    except ValueError:
        raise RuntimeError(
            "DATABASE_URL is invalid; check the private connection settings."
        ) from None
    if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
        raise RuntimeError("DATABASE_URL must use PostgreSQL.")
    # Neon pooled connections use transaction pooling.
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
elif not DEBUG:
    raise RuntimeError("Set DATABASE_URL for the production PostgreSQL database.")
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
if DEBUG:
    CSRF_TRUSTED_ORIGINS += ["http://127.0.0.1:5173", "http://localhost:5173"]
SECURE_SSL_REDIRECT = not DEBUG
# Only enable behind Render's TLS-terminating proxy, never on an exposed server.
if os.environ.get("CM_TRUST_RENDER_PROXY") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "no-referrer"
EMAIL_BACKEND = os.environ.get(
    "CM_EMAIL_BACKEND",
    "django.core.mail.backends.filebased.EmailBackend"
    if DEBUG
    else "core.email_backend.ResendEmailBackend",
)
EMAIL_FILE_PATH = BASE_DIR.parent / ".local" / "mail"
EMAIL_HOST = os.environ.get("CM_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("CM_EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("CM_EMAIL_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("CM_EMAIL_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("CM_EMAIL_TLS", "1") == "1"
EMAIL_TIMEOUT = 10
RESEND_API_KEY = os.environ.get("CM_RESEND_API_KEY", "")
RESEND_TEST_RECIPIENT = os.environ.get("CM_RESEND_TEST_RECIPIENT", "").strip().lower()
DEFAULT_FROM_EMAIL = os.environ.get("CM_FROM_EMAIL", "CM <noreply@example.com>")
LANGUAGE_CODE = "zh-hant"
TIME_ZONE = "Asia/Taipei"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
