"""``manage.py bootstrap_admin`` — create the first superuser from environment variables (idempotent).

Railway has no shell on the Hobby plan, so the schema step creates the initial
administrator when ``ADMIN_EMAIL`` and ``ADMIN_PASSWORD`` are set. The account
is created only if that email does not exist yet; the password is never
changed afterwards, so the variables can be removed once the account works.
"""
import os

from django.core.management.base import BaseCommand

from apps.accounts.models import User


class Command(BaseCommand):
    """Create the superuser named by ADMIN_EMAIL / ADMIN_PASSWORD if absent."""

    help = "Create the initial superuser from ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME (no-op when unset or existing)."

    def handle(self, *args, **options):
        """Create the account, or report why nothing was done."""
        email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD") or ""
        if not email or not password:
            self.stdout.write("bootstrap_admin: ADMIN_EMAIL/ADMIN_PASSWORD not set — skipped")
            return
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"bootstrap_admin: {email} exists — unchanged")
            return
        User.objects.create_superuser(email=email, password=password, full_name=os.environ.get("ADMIN_NAME", "Administrator"))
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created superuser {email}"))
