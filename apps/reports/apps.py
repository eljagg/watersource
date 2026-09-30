"""App configuration for business intelligence."""
from django.apps import AppConfig


class ReportsConfig(AppConfig):
    """Registers the reports app."""
    name = "apps.reports"
    verbose_name = "Business intelligence"
