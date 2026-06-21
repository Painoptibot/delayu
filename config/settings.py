"""

Настройки проекта newsystem — платформа «ДелаЮ».

PostgreSQL обязателен (см. .env и scripts/setup_postgresql.py).

"""

from pathlib import Path



from dotenv import load_dotenv

import os



from .template import TEMPLATE_CONFIG, THEME_LAYOUT_DIR, THEME_VARIABLES



BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")



SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-insecure-change-me")

DEBUG = os.getenv("DEBUG", "true").lower() in ("1", "true", "yes")

ALLOWED_HOSTS = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

CSRF_FAILURE_VIEW = "delayu.views_auth.csrf_failure"

ENVIRONMENT = os.getenv("DJANGO_ENVIRONMENT", "local")



INSTALLED_APPS = [

    "django.contrib.admin",

    "django.contrib.auth",

    "django.contrib.contenttypes",

    "django.contrib.sessions",

    "django.contrib.messages",

    "django.contrib.staticfiles",

    "delayu",

    "apps.pages",

    "core",

]



MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "delayu.middleware.platform.CorrelationIdMiddleware",
    "delayu.middleware.platform.ActiveMembershipMiddleware",
    "delayu.middleware.platform.TwoFactorMiddleware",
    "delayu.middleware.platform.SessionRegistryMiddleware",
    "delayu.middleware.platform.DemoModeMiddleware",
    "delayu.middleware.platform.PrivacyModeAuditMiddleware",
]



ROOT_URLCONF = "config.urls"



TEMPLATES = [

    {

        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [BASE_DIR / "templates"],

        "APP_DIRS": True,

        "OPTIONS": {

            "context_processors": [

                "django.template.context_processors.debug",

                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",

                "django.contrib.messages.context_processors.messages",

                "config.context_processors.my_setting",

                "config.context_processors.get_cookie",

                "config.context_processors.environment",
                "config.context_processors.delayu_nav",
                "config.context_processors.delayu_tz",
                "config.context_processors.yandex_maps",
                "config.context_processors.dadata_integration",

            ],

            "libraries": {

                "theme": "web_project.template_tags.theme",

            },

            "builtins": [

                "django.templatetags.static",

                "web_project.template_tags.theme",

            ],

        },

    },

]



WSGI_APPLICATION = "config.wsgi.application"

ASGI_APPLICATION = "config.asgi.application"



DATABASES = {

    "default": {

        "ENGINE": "django.db.backends.postgresql",

        "NAME": os.getenv("POSTGRES_DB", "newsystem"),

        "USER": os.getenv("POSTGRES_USER", "newsystem"),

        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "newsystem"),

        "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),

        "PORT": os.getenv("POSTGRES_PORT", "5432"),

    }

}



AUTH_PASSWORD_VALIDATORS = [

    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},

    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},

    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},

    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},

]



LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True

USE_TZ = True



STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [BASE_DIR / "src" / "assets"]



MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"



DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"



LOGIN_URL = "login"

LOGIN_REDIRECT_URL = "platform-home"

LOGOUT_REDIRECT_URL = "login"



LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": "%(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "delayu.request": {"handlers": ["console"], "level": "INFO"},
        "delayu.security": {"handlers": ["console"], "level": "WARNING"},
    },
}


SENTRY_DSN = os.getenv("SENTRY_DSN", "")
if SENTRY_DSN and not DEBUG:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()], traces_sample_rate=0.1)
    except ImportError:
        pass

TEMPLATE_CONFIG = TEMPLATE_CONFIG

THEME_LAYOUT_DIR = THEME_LAYOUT_DIR

THEME_VARIABLES = THEME_VARIABLES


# Почта (глобальный SMTP; подсистема может переопределить в Эксплуатация → Почта)
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "1025"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "false").lower() in ("1", "true", "yes")
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@delayu.local")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Web Push (АИС УЖВ) — ключи VAPID из .env; пусто = только локальные уведомления
UZHV_VAPID_PUBLIC_KEY = os.getenv("UZHV_VAPID_PUBLIC_KEY", "")
UZHV_VAPID_PRIVATE_KEY = os.getenv("UZHV_VAPID_PRIVATE_KEY", "")

# Яндекс.Карты (карта жилфонда УЖВ, геокодирование адресов МКД)
YANDEX_MAPS_API_KEY = os.getenv("YANDEX_MAPS_API_KEY", "")

# DaData — подсказки адреса, ФИО, телефона и др. (ключ: https://dadata.ru/profile/#info)
DADATA_API_KEY = os.getenv("DADATA_API_KEY", "")
DADATA_SECRET_KEY = os.getenv("DADATA_SECRET_KEY", "")

# Telegram Bot API (опционально; иначе token из MessengerChannel.webhook_url)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
DELAYU_TELEGRAM_DEMO_LOG = os.getenv("DELAYU_TELEGRAM_DEMO_LOG", "true").lower() in (
    "1",
    "true",
    "yes",
)
DELAYU_WEBHOOK_URL = os.getenv("DELAYU_WEBHOOK_URL", "")
DELAYU_WEBHOOK_SECRET = os.getenv("DELAYU_WEBHOOK_SECRET", "")
DELAYU_N8N_WEBHOOK_URL = os.getenv("DELAYU_N8N_WEBHOOK_URL", "")

# Публичная форма обращений УЖВ (пусто = без токена, только для dev)
UZHV_PUBLIC_APPEAL_TOKEN = os.getenv("UZHV_PUBLIC_APPEAL_TOKEN", "")

# Версия платформы для паспорта продукта и реестра
DELAYU_PLATFORM_VERSION = os.getenv("DELAYU_PLATFORM_VERSION", "2.2.0")

# #6 — глобальный read-only демо-режим (дополняет PiiMaskingPolicy.demo_mode на подсистему)
DELAYU_DEMO_MODE = os.getenv("DELAYU_DEMO_MODE", "false").lower() in ("1", "true", "yes")

# Production (DEBUG=false): HTTPS за reverse-proxy
if not DEBUG:
    if not CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS = [
            f"https://{host}"
            for host in ALLOWED_HOSTS
            if host and not host.replace(".", "").isdigit()
        ]
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    _hsts = os.getenv("SECURE_HSTS_SECONDS", "")
    if _hsts.isdigit() and int(_hsts) > 0:
        SECURE_HSTS_SECONDS = int(_hsts)
        SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv(
            "SECURE_HSTS_INCLUDE_SUBDOMAINS", "false"
        ).lower() in ("1", "true", "yes")
