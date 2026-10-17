"""Create the default milestone records (idempotent; never changes a milestone that exists)."""
from django.core.management.base import BaseCommand

from apps.governance.models import DEFAULT_MILESTONES, Milestone


class Command(BaseCommand):
    """``manage.py bootstrap_milestones`` — runs at every deploy from the entrypoint."""

    help = __doc__

    def handle(self, *args, **opts):
        """Create what is missing."""
        made = 0
        for number, code, week, title, desc in DEFAULT_MILESTONES:
            _, created = Milestone.objects.get_or_create(number=number, defaults={"code": code, "due_week": week, "title": title, "description": desc})
            made += int(created)
        self.stdout.write(f"milestones {made} created, {len(DEFAULT_MILESTONES) - made} existed")
