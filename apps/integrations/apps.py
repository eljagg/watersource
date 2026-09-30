"""App configuration for integrations."""
from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    """Registers the integrations app."""
    name = "apps.integrations"
    verbose_name = "Integrations and exports"
