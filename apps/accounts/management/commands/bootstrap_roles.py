from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts import roles


class Command(BaseCommand):
    help = "Create the fixed role groups (idempotent)."

    def handle(self, *args, **options):
        for name in roles.ALL:
            _, created = Group.objects.get_or_create(name=name)
            self.stdout.write(f"{'created' if created else 'exists '} {name}")
