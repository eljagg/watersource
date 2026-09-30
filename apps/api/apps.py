"""App configuration for the REST API."""
from django.apps import AppConfig


class ApiConfig(AppConfig):
    """Registers the api app."""
    name = "apps.api"
    verbose_name = "REST API"
