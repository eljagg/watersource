"""
WaterSource Jamaica — base settings.

Project: WRA RFB No. 2026-08-28-WRA-B, Data Consolidation and Application
Development Software and Services.  One Django project, two user-facing
applications (Licence Application Processing, Data Submission) on one
consolidated PostgreSQL/PostGIS database.

Environment-specific values come from environment variables (see .env.example).
Never put secrets in this file.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    CSRF_TRUSTED_ORIGINS=(list, []),
    REDIS_URL=(str, "redis://localhost:6379/0"),
    EMAIL_URL=(str, "consolemail://"),
    DEFAULT_FROM_EMAIL=(str, "WaterSource Jamaica <no-reply@wra.gov.jm>"),
    SITE_URL=(str, "http://localhost:8000"),
    STAFF_PASSWORD_MAX_AGE_DAYS=(int, 90),
    SESSION_IDLE_MINUTES=(int, 20),
    SESSION_ABSOLUTE_HOURS=(int, 8),
    AXES_FAILURE_LIMIT=(int, 5),
    AXES_COOLOFF_MINUTES=(int, 15),
    CLAMAV_HOST=(str, ""),
    CLAMAV_PORT=(int, 3310),
    DSPACE_URL=(str, ""),
    DSPACE_USER=(str, ""),
    DSPACE_PASSWORD=(str, ""),
    DSPACE_COLLECTION_ID=(str, ""),
    AQUARIUS_URL=(str, ""),
    AQUARIUS_USER=(str, ""),
    AQUARIUS_PASSWORD=(str, ""),
    HGA_ODBC_DSN=(str, ""),
    EXPORT_DIR=(str, str(BASE_DIR / "exports")),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="insecure-dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
SITE_URL = env("SITE_URL")

# ----------------------------------------------------------------------------
# Applications
# ----------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
]
THIRD_PARTY_APPS = [
    "rest_framework",
    "drf_spectacular",
    "django_filters",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "axes",
    "csp",
    "template_partials",
]
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.ref",
    "apps.obs",
    "apps.catalog",
    "apps.workflow",
    "apps.lic",
    "apps.submissions",
    "apps.integrations",
    "apps.api",
    "apps.reports",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "apps.accounts.middleware.SessionPolicyMiddleware",
    "apps.accounts.middleware.PasswordPolicyMiddleware",
    "apps.accounts.middleware.MFAEnforcementMiddleware",
    "apps.core.middleware.CurrentUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "csp.middleware.CSPMiddleware",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.site",
            ],
        },
    }
]

# ----------------------------------------------------------------------------
# Database — one consolidated PostgreSQL 16 + PostGIS database (ToR H.xv)
# ----------------------------------------------------------------------------
DATABASES = {
    "default": env.db_url("DATABASE_URL", default="postgis://ws:ws@localhost:5432/watersource"),
}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"].update({"connect_timeout": 5})
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ----------------------------------------------------------------------------
# Cache / Celery
# ----------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": "ws",
        "TIMEOUT": 300,
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_TASK_ALWAYS_EAGER", default=False)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "America/Jamaica"
CELERY_BEAT_SCHEDULE = {
    "licence-expiry-alerts": {"task": "apps.lic.tasks.raise_expiry_alerts", "schedule": timedelta(hours=24)},
    "refresh-bi-views": {"task": "apps.reports.tasks.refresh_bi_views", "schedule": timedelta(hours=24)},
    "aquarius-sync": {"task": "apps.integrations.tasks.sync_aquarius", "schedule": timedelta(hours=24)},
    "hga-sync": {"task": "apps.integrations.tasks.sync_hga", "schedule": timedelta(hours=24)},
    "arcgis-export": {"task": "apps.integrations.tasks.export_arcgis", "schedule": timedelta(hours=24)},
    "retention-sweep": {"task": "apps.accounts.tasks.retention_sweep", "schedule": timedelta(days=1)},
}

# ----------------------------------------------------------------------------
# Authentication — application-managed accounts only (ToR H.i–v)
# ----------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {"NAME": "apps.accounts.validators.ComplexityValidator"},
    {"NAME": "apps.accounts.validators.PasswordHistoryValidator", "OPTIONS": {"history": 10}},
]
STAFF_PASSWORD_MAX_AGE_DAYS = env("STAFF_PASSWORD_MAX_AGE_DAYS")
MFA_REQUIRED_GROUPS = ["approver", "administrator"]

# django-axes: lockout after repeated failures (ToR H.iii)
AXES_FAILURE_LIMIT = env("AXES_FAILURE_LIMIT")
AXES_COOLOFF_TIME = timedelta(minutes=env("AXES_COOLOFF_MINUTES"))
AXES_LOCKOUT_PARAMETERS = ["username", ["ip_address", "user_agent"]]
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "accounts/locked_out.html"
AXES_ENABLE_ACCESS_FAILURE_LOG = True

# Sessions (ToR §9 session timeout controls)
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env("SESSION_ABSOLUTE_HOURS") * 3600
SESSION_IDLE_MINUTES = env("SESSION_IDLE_MINUTES")
SESSION_SAVE_EVERY_REQUEST = False
CSRF_COOKIE_HTTPONLY = False  # htmx reads the token from the cookie/meta tag
CSRF_COOKIE_SAMESITE = "Lax"

# ----------------------------------------------------------------------------
# Security headers / CSP (ToR §9: XSS, CSRF, clickjacking)
# ----------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'", "'nonce'"),  # nonce added by csp middleware; no inline scripts
        "style-src": ("'self'", "'unsafe-inline'"),  # Tailwind utility classes; tighten at build stage
        "img-src": ("'self'", "data:", "blob:"),
        "font-src": ("'self'",),
        "connect-src": ("'self'",),
        "frame-ancestors": ("'none'",),
        "form-action": ("'self'",),
        "base-uri": ("'self'",),
        "object-src": ("'none'",),
    }
}

# ----------------------------------------------------------------------------
# Uploads (ToR §9 file upload validation, malware scanning)
# ----------------------------------------------------------------------------
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
MEDIA_URL = "/media/"  # served only through the protected download view, never directly
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
UPLOAD_MAX_BYTES = 25 * 1024 * 1024
UPLOAD_ALLOWED_TYPES = {
    "application/pdf": [".pdf"],
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "text/csv": [".csv"],
    "text/plain": [".csv", ".txt"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
}
CLAMAV_HOST = env("CLAMAV_HOST")
CLAMAV_PORT = env("CLAMAV_PORT")
EXPORT_DIR = env("EXPORT_DIR")

# ----------------------------------------------------------------------------
# Static files
# ----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ----------------------------------------------------------------------------
# Email (ToR H.xi notifications by email and in-app)
# ----------------------------------------------------------------------------
vars().update(env.email_url("EMAIL_URL"))
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ----------------------------------------------------------------------------
# REST API (ToR F.7, H.xii)
# ----------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.APIKeyAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticatedOrReadOnly"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.AnonRateThrottle", "rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "user": "600/min", "api_key": "1200/min"},
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
SPECTACULAR_SETTINGS = {
    "TITLE": "WaterSource Jamaica API",
    "DESCRIPTION": "Consolidated water-resources database API — Water Resources Authority of Jamaica.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ----------------------------------------------------------------------------
# Integrations (all optional; empty = disabled)
# ----------------------------------------------------------------------------
DSPACE = {
    "URL": env("DSPACE_URL"),
    "USER": env("DSPACE_USER"),
    "PASSWORD": env("DSPACE_PASSWORD"),
    "COLLECTION_ID": env("DSPACE_COLLECTION_ID"),
}
AQUARIUS = {"URL": env("AQUARIUS_URL"), "USER": env("AQUARIUS_USER"), "PASSWORD": env("AQUARIUS_PASSWORD")}
HGA_ODBC_DSN = env("HGA_ODBC_DSN")

# ----------------------------------------------------------------------------
# Domain settings
# ----------------------------------------------------------------------------
WATERSOURCE = {
    "SRID_STORAGE": 3448,  # JAD2001 / Jamaica Metric Grid
    "SRID_EXPORT": 4326,
    "LICENCE_EXPIRY_WARNING_DAYS": [90, 30, 7],
    "RETENTION": {
        "LICENCE_DATA_YEARS_AFTER_EXPIRY": 7,
        "INACTIVE_CLIENT_ACCOUNT_MONTHS": 24,
        "REJECTED_APPLICATION_YEARS": 3,
    },
    "APPLICATION_REF_PREFIX": "WRA-LA",
    "LICENCE_NO_PREFIX": "WRA-L",
}

# ----------------------------------------------------------------------------
# i18n / logging
# ----------------------------------------------------------------------------
LANGUAGE_CODE = "en-jm"
TIME_ZONE = "America/Jamaica"
USE_I18N = True
USE_TZ = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.JSONFormatter",
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.security": {"level": "INFO"},
        "axes": {"level": "INFO"},
        "watersource.audit": {"level": "INFO"},
    },
}
