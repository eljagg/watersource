from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
AXES_ENABLED = env.bool("AXES_ENABLED", default=True)  # noqa: F405
