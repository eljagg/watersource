"""``manage.py bootstrap_roles`` — create the fixed role groups from ``accounts.roles`` and the WRA units from ``accounts.units`` (idempotent; runs on every deploy)."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts import roles
from apps.accounts.models import Unit
from apps.accounts.units import WRA_UNITS


class Command(BaseCommand):
    """Create any missing role group."""
    help = "Create the fixed role groups (idempotent)."

    def handle(self, *args, **options):
        """Create each group in ``roles.ALL`` if absent and report."""
        for name in roles.ALL:
            _, created = Group.objects.get_or_create(name=name)
            self.stdout.write(f"{'created' if created else 'exists '} {name}")
        for code, name, division, operating, modules, has_su, owns in WRA_UNITS:
            _, created = Unit.objects.update_or_create(
                code=code, defaults=dict(name=name, division=division, is_operating=operating, primary_modules=modules, has_super_user=has_su, responsibilities=owns[:255]),
            )
            self.stdout.write(f"{'created' if created else 'exists '} unit {code} {name}")
