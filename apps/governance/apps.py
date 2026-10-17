"""Governance app (v0.13.0, stakeholder model package 4): executive view and milestone acceptance log."""
from django.apps import AppConfig


class GovernanceConfig(AppConfig):
    """App config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.governance"
    verbose_name = "Governance"
