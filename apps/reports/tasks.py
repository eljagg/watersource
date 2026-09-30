"""Celery tasks for the ``bi`` schema (design doc 13 §6: data refresh every 5 minutes)."""
from celery import shared_task

from . import services


@shared_task
def refresh_bi_views() -> list[str]:
    """Refresh every materialised view in the bi schema; returns the names refreshed."""
    return services.refresh_all()
