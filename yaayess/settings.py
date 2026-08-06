"""
Configuration Django du projet YAAYESS.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


# ==========================================================
# CHEMINS ET VARIABLES D'ENVIRONNEMENT
# ==========================================================

BASE_DIR = Path(__file__).resolve().parent.parent

# En local, charge BASE_DIR/.env.
# Sur le VPS, les variables définies par systemd restent prioritaires.
load_dotenv(BASE_DIR / ".env", override=False)


def env_bool(name: str, default: bool = False) -> bool:
    """
    Convertit une variable d'environnement en booléen.
    """
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def env_list(name: str, default: str = "") -> list[str]:
    """
    Convertit une variable séparée par des virgules en liste.
    """
    raw_value = os.getenv(name, default)

    return [
        value.strip()
        for value in raw_value.split(",")
        if value.strip()
    ]


# ==========================================================
# CONFIGURATION GÉNÉRALE
# ==========================================================

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = env_bool(
    "DEBUG",
    default=False,
)

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default=(
        "localhost,"
        "127.0.0.1,"
        "yaayess-ngen.shop,"
        "www.yaayess-ngen.shop"
    ),
)


# ==========================================================
# OPENAI
# ==========================================================

OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY",
    "",
)


# ==========================================================
# BASE DE DONNÉES
# ==========================================================

DATABASES = {
    "default": {
        "ENGINE": os.getenv(
            "DB_ENGINE",
            "django.db.backends.postgresql",
        ),
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.getenv(
            "DB_HOST",
            "127.0.0.1",
        ),
        "PORT": os.getenv(
            "DB_PORT",
            "5432",
        ),
        "CONN_MAX_AGE": int(
            os.getenv(
                "DB_CONN_MAX_AGE",
                "60",
            )
        ),
    }
}


# ==========================================================
# APPLICATIONS
# ==========================================================

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Applications tierces
    "django_countries",
    "rest_framework",
    "widget_tweaks",
    "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
    "whitenoise.runserver_nostatic",

    # Applications YAAYESS
    "accounts.apps.AccountsConfig",
    "cotisationtontine.apps.CotisationtontineConfig",
    "epargnecredit",
    "pilotage",
    "legal",
]

# Le serveur SSL Django est réservé au développement local.
if DEBUG:
    INSTALLED_APPS.append("sslserver")


# ==========================================================
# MIDDLEWARE
# ==========================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    # CORS doit être placé avant CommonMiddleware.
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    "legal.middleware.TermsGateMiddleware",
]


# ==========================================================
# URLS ET SERVEURS
# ==========================================================

ROOT_URLCONF = "yaayess.urls"

WSGI_APPLICATION = "yaayess.wsgi.application"


# ==========================================================
# TEMPLATES
# ==========================================================

TEMPLATES = [
    {
        "BACKEND": (
            "django.template.backends.django."
            "DjangoTemplates"
        ),
        "DIRS": [
            BASE_DIR / "templates",
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                (
                    "django.template.context_processors."
                    "debug"
                ),
                (
                    "django.template.context_processors."
                    "request"
                ),
                (
                    "django.template.context_processors."
                    "csrf"
                ),
                (
                    "django.contrib.auth.context_processors."
                    "auth"
                ),
                (
                    "django.contrib.messages.context_processors."
                    "messages"
                ),
            ],
        },
    },
]


# ==========================================================
# UTILISATEUR ET AUTHENTIFICATION
# ==========================================================

AUTH_USER_MODEL = "accounts.CustomUser"

AUTHENTICATION_BACKENDS = [
    "accounts.auth_backend.PhoneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/tontine/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"


# ==========================================================
# SESSION
# ==========================================================

SESSION_COOKIE_AGE = 3600
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"


# ==========================================================
# CSRF
# ==========================================================

CSRF_TRUSTED_ORIGINS = [
    "https://yaayess-ngen.shop",
    "https://www.yaayess-ngen.shop",
]

if DEBUG:
    CSRF_TRUSTED_ORIGINS += [
        "http://127.0.0.1",
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://localhost:8000",
        "http://localhost:3000",
    ]

CSRF_COOKIE_SAMESITE = "Lax"


# ==========================================================
# SÉCURITÉ HTTPS
# ==========================================================

# Permet à Django de reconnaître HTTPS derrière Nginx.
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_REFERRER_POLICY = "same-origin"

if DEBUG:
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False

    SECURE_SSL_REDIRECT = False

    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

else:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = True

    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True


# ==========================================================
# DJANGO REST FRAMEWORK
# ==========================================================

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        (
            "rest_framework_simplejwt."
            "authentication.JWTAuthentication"
        ),
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}


# ==========================================================
# JWT
# ==========================================================

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=15,
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=7,
    ),

    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": (
        "Bearer",
    ),
}


# ==========================================================
# CORS
# ==========================================================

# Autorisation large uniquement en développement.
CORS_ALLOW_ALL_ORIGINS = DEBUG

if not DEBUG:
    CORS_ALLOWED_ORIGINS = env_list(
        "CORS_ALLOWED_ORIGINS",
        default=(
            "https://yaayess-ngen.shop,"
            "https://www.yaayess-ngen.shop"
        ),
    )

CORS_ALLOW_CREDENTIALS = True


# ==========================================================
# EMAIL — BREVO
# ==========================================================

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = os.getenv(
    "EMAIL_HOST",
    "smtp-relay.brevo.com",
)

EMAIL_PORT = int(
    os.getenv(
        "EMAIL_PORT",
        "587",
    )
)

EMAIL_USE_TLS = env_bool(
    "EMAIL_USE_TLS",
    default=True,
)

EMAIL_USE_SSL = env_bool(
    "EMAIL_USE_SSL",
    default=False,
)

EMAIL_HOST_USER = os.getenv(
    "EMAIL_HOST_USER",
    "",
)

EMAIL_HOST_PASSWORD = os.getenv(
    "BREVO_SMTP_KEY",
    "",
)

DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL",
    EMAIL_HOST_USER or "no-reply@yaayess-ngen.shop",
)


# ==========================================================
# TWILIO
# ==========================================================

TWILIO_ACCOUNT_SID = os.getenv(
    "TWILIO_ACCOUNT_SID",
    "",
)

TWILIO_AUTH_TOKEN = os.getenv(
    "TWILIO_AUTH_TOKEN",
    "",
)

TWILIO_PHONE_NUMBER = os.getenv(
    "TWILIO_PHONE_NUMBER",
    "",
)


# ==========================================================
# INTERNATIONALISATION
# ==========================================================

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "Africa/Dakar"

USE_I18N = True
USE_TZ = True


# ==========================================================
# FICHIERS STATIQUES
# ==========================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STORAGES = {
    "default": {
        "BACKEND": (
            "django.core.files.storage."
            "FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },
}


# ==========================================================
# FICHIERS MÉDIAS
# ==========================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ==========================================================
# LIMITES D'UPLOAD
# ==========================================================

DATA_UPLOAD_MAX_MEMORY_SIZE = (
    15 * 1024 * 1024
)

FILE_UPLOAD_MAX_MEMORY_SIZE = (
    10 * 1024 * 1024
)


# ==========================================================
# CONDITIONS GÉNÉRALES
# ==========================================================

TERMS_VERSION = os.getenv(
    "TERMS_VERSION",
    "v1.0-2025-09-07",
)


# =====================================================
# PAYDUNYA
# =====================================================

PAYDUNYA_MODE = os.getenv(
    "PAYDUNYA_MODE",
    "test",
).strip().lower()

PAYDUNYA_MASTER_KEY = os.getenv(
    "PAYDUNYA_MASTER_KEY",
    "",
)

PAYDUNYA_PUBLIC_KEY = os.getenv(
    "PAYDUNYA_PUBLIC_KEY",
    "",
)

PAYDUNYA_PRIVATE_KEY = os.getenv(
    "PAYDUNYA_PRIVATE_KEY",
    "",
)

PAYDUNYA_TOKEN = os.getenv(
    "PAYDUNYA_TOKEN",
    "",
)

PAYDUNYA_STORE_NAME = os.getenv(
    "PAYDUNYA_STORE_NAME",
    "YAAYESS",
)

PAYDUNYA_STORE_TAGLINE = os.getenv(
    "PAYDUNYA_STORE_TAGLINE",
    "",
)

PAYDUNYA_STORE_PHONE = os.getenv(
    "PAYDUNYA_STORE_PHONE",
    "",
)

PAYDUNYA_STORE_WEBSITE = os.getenv(
    "PAYDUNYA_STORE_WEBSITE",
    "",
)

PAYDUNYA_STORE_LOGO = os.getenv(
    "PAYDUNYA_STORE_LOGO",
    "",
)

PAYDUNYA_RETURN_URL = os.getenv(
    "PAYDUNYA_RETURN_URL",
    "",
)

PAYDUNYA_CANCEL_URL = os.getenv(
    "PAYDUNYA_CANCEL_URL",
    "",
)

PAYDUNYA_CALLBACK_URL = os.getenv(
    "PAYDUNYA_CALLBACK_URL",
    "",
)


# ==========================================================
# MODÈLES DJANGO
# ==========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"