"""App configuration for the category framework."""
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    """Registers the catalog app."""
    name = "apps.catalog"
    verbose_name = "Data categories (templates)"
