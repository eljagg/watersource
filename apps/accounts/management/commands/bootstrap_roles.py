"""``manage.py bootstrap_roles`` — create the fixed role groups from ``accounts.roles`` (idempotent; runs on every deploy)."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts import roles


class Command(BaseCommand):
    """Create any missing role group."""
    help = "Create the fixed role groups (idempotent)."

    def handle(self, *args, **options):
        """Create each group in ``roles.ALL`` if absent and report."""
        for name in roles.ALL:
            _, created = Group.objects.get_or_create(name=name)
            self.stdout.write(f"{'created' if created else 'exists '} {name}")
