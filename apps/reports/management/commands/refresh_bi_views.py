"""``manage.py refresh_bi_views`` — refresh the bi schema now (deploy step and manual use)."""
from django.core.management.base import BaseCommand

from apps.reports import services


class Command(BaseCommand):
    """Refresh all materialised views in the bi schema."""

    help = "Refresh every materialised view in the bi schema."

    def handle(self, *args, **options):
        """Refresh and list the views."""
        for view in services.refresh_all():
            self.stdout.write(f"refreshed {view}")
