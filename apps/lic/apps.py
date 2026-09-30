"""App configuration for licensing."""
from django.apps import AppConfig


class LicConfig(AppConfig):
    """Registers the lic app."""
    name = "apps.lic"
    verbose_name = "Licensing"
