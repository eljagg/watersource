"""Unit console (v0.8.0): the Super User's desk — stakeholder model package 2 (design doc 17)."""
from django.apps import AppConfig


class ConsoleConfig(AppConfig):
    """App config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.console"
    verbose_name = "Unit console"
