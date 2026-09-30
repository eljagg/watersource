"""App configuration for data submissions."""
from django.apps import AppConfig


class SubmissionsConfig(AppConfig):
    """Registers the submissions app."""
    name = "apps.submissions"
    verbose_name = "Data submissions"
