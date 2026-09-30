"""App configuration for reference data."""
from django.apps import AppConfig


class RefConfig(AppConfig):
    """Registers the ref app."""
    name = "apps.ref"
    verbose_name = "Reference and master data"
