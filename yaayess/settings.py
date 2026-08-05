import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

# Charge .env le plus tôt possible (et écrase les valeurs vides du système si besoin)
load_dotenv(BASE_DIR / ".env", override=True)

#ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# ---- ensuite seulement, lis tes variables ----
SECRET_KEY = os.environ["SECRET_KEY"]                 # déjà dans ton .env
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")          # ⬅️ lira bien la valeur du .env
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY manquante. Vérifie .env ou les variables d'environnement.")

CSRF_TRUSTED_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:3000",
]

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

EMAIL_HOST = 'smtp-relay.brevo.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = 'a5d583001@smtp-brevo.com'


EMAIL_HOST_PASSWORD = os.getenv("BREVO_SMTP_KEY")

# ----------------------------------------------------
# 🗄 DATABASE - Version sécurisée
# ----------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": os.getenv(
            "DB_ENGINE",
            "django.db.backends.postgresql",
        ),
        "NAME": os.environ["DB_NAME"],
        "USER": os.environ["DB_USER"],
        "PASSWORD": os.environ["DB_PASSWORD"],
        "HOST": os.getenv("DB_HOST", "127.0.0.1"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}


SESSION_COOKIE_AGE = 3600  # 1 heure
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = False  # True en production HTTPS
SESSION_COOKIE_HTTPONLY = True

# PROD security (activés automatiquement quand DEBUG=False)
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
#    SESSION_COOKIE_SECURE = True
#    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

DEBUG = True

CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False


# sécurité production
if not DEBUG:

    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SECURE_SSL_REDIRECT = True

    SESSION_COOKIE_SECURE = True

    CSRF_COOKIE_SECURE = True

    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ----------------------------------------------------
# 🌍 OPENAI
# ----------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ----------------------------------------------------
# 📦 INSTALLED APPS (inchangé)
# ----------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    "django_countries",
    # Apps locales
    'cotisationtontine.apps.CotisationtontineConfig',
    'pilotage',
    'community_investment.apps.CommunityInvestmentConfig',
    'governance.apps.GovernanceConfig',

    'epargnecredit',
    'legal',
    'rest_framework',
    'widget_tweaks',


    # Outils
    'whitenoise.runserver_nostatic',
    'sslserver',
    "corsheaders",
    'rest_framework_simplejwt.token_blacklist',
    'accounts.apps.AccountsConfig',


]

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),

    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,

    "UPDATE_LAST_LOGIN": True,

    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,

    "AUTH_HEADER_TYPES": ("Bearer",),
}


CORS_ALLOW_ALL_ORIGINS = True


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}


# SIMPLE_JWT = {
#    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
#    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
#    'AUTH_HEADER_TYPES': ('Bearer',),
#}

AUTH_USER_MODEL = "accounts.CustomUser"


TERMS_VERSION = "v1.0-2025-09-07"


AUTHENTICATION_BACKENDS = [
    "accounts.backends.PhoneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# ----------------------------------------------------
# ⚙️ MIDDLEWARE
# ----------------------------------------------------

MIDDLEWARE = [

    'django.middleware.security.SecurityMiddleware',

    'whitenoise.middleware.WhiteNoiseMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',

    'corsheaders.middleware.CorsMiddleware',

    'django.middleware.common.CommonMiddleware',

    'django.middleware.csrf.CsrfViewMiddleware',

    'django.contrib.auth.middleware.AuthenticationMiddleware',

    'django.contrib.messages.middleware.MessageMiddleware',

    'django.middleware.clickjacking.XFrameOptionsMiddleware',

    "legal.middleware.TermsGateMiddleware",

]

ROOT_URLCONF = 'yaayess.urls'
WSGI_APPLICATION = 'yaayess.wsgi.application'

# Templates : vérifie bien l’entrée DIRS → "templates/"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],   # ✅ important pour templates/assistant_ai/...
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",  # ✅
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# EMAIL
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'tonemail@gmail.com'
EMAIL_HOST_PASSWORD = 'mot_de_passe'
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# TWILIO
TWILIO_ACCOUNT_SID = "xxxx"
TWILIO_AUTH_TOKEN = "xxxx"
TWILIO_PHONE_NUMBER = "+123456789"



# ----------------------------------------------------
# 🔑 AUTHENTICATION
# ----------------------------------------------------

#AUTH_USER_MODEL = 'accounts.CustomUser'
#LOGIN_URL = '/login/'
#LOGIN_REDIRECT_URL = '/'
#LOGOUT_REDIRECT_URL = '/'

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/tontine/dashboard/'
LOGOUT_REDIRECT_URL = '/accounts/login/'


# ----------------------------------------------------
# 🌍 INTERNATIONALIZATION
# ----------------------------------------------------
LANGUAGE_CODE = 'fr-fr'
TIME_ZONE = 'Africa/Dakar'
USE_I18N = True
USE_TZ = True

# ----------------------------------------------------
# 📁 STATIC & MEDIA FILES
# ----------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ----------------------------------------------------
# 🔒 SECURITY HEADERS (Production)
# ----------------------------------------------------
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# AUTHENTICATION_BACKENDS = [
#    'accounts.backends.NomBackend',
#]
AUTHENTICATION_BACKENDS = [
    'accounts.auth_backend.PhoneBackend',
]


# settings.py
LOGIN_URL = '/accounts/login/'          # redirection pour utilisateurs non connectés
LOGIN_REDIRECT_URL = '/groups/'         # redirection après login réussi

# Uploads audio (sécu & confort)
DATA_UPLOAD_MAX_MEMORY_SIZE = 15 * 1024 * 1024  # 15 Mo
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 Mo


# Dev only: servir /media
if DEBUG:
    from django.conf.urls.static import static
    from django.conf import settings as _s
    urlpatterns = []
    urlpatterns += static(_s.MEDIA_URL, document_root=_s.MEDIA_ROOT)


