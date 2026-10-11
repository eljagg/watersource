"""Public repository and open-data views (v0.9.0) — stakeholder model package 3 (design doc 17)."""
from django.apps import AppConfig


class OpendataConfig(AppConfig):
    """App config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.opendata"
    verbose_name = "Public repository"
