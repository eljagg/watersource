"""App configuration for observations."""
from django.apps import AppConfig


class ObsConfig(AppConfig):
    """Registers the obs app."""
    name = "apps.obs"
    verbose_name = "Observations"
