r"""``manage.py import_model_output`` — load a SWAT+, Wflow or generic model result file as a Model output submission.

Example::

    manage.py import_model_output --format swatplus --run riocobre-swatplus-2026a \\
        --user hydrologist@wra.gov.jm --map "12=Bog Walk,7=Flat Bridge" channel_sd_day.txt

The file goes through the normal submission path (validation → review queue →
promotion), so a reviewer still approves it before it appears on dashboards.
"""
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import DataCategory
from apps.obs.model_adapters import ADAPTERS, parse_map
from apps.obs.models import ModelRun
from apps.submissions.models import Channel
from apps.submissions.services import create_submission


class Command(BaseCommand):
    """Import one model output file."""

    help = "Load a model output file (SWAT+ channel_sd_day.txt, Wflow CSV or category CSV) as a Model output submission."

    def add_arguments(self, parser):
        """CLI options."""
        parser.add_argument("file", help="Path to the output file")
        parser.add_argument("--format", choices=sorted(ADAPTERS), default="generic")
        parser.add_argument("--run", required=True, help="ModelRun code (create it in the admin console first)")
        parser.add_argument("--user", required=True, help="Email of the staff user the submission is recorded against")
        parser.add_argument("--map", default="", help='Model element id → station name, e.g. "12=Bog Walk,7=Flat Bridge"')
        parser.add_argument("--note", default="")

    def handle(self, *args, **opts):
        """Parse, validate and create the submission."""
        if not ModelRun.objects.filter(code=opts["run"]).exists():
            raise CommandError(f"No model run with code {opts['run']!r}. Create it under Admin console → Observations → Model runs.")
        user = get_user_model().objects.filter(email__iexact=opts["user"]).first()
        if user is None:
            raise CommandError(f"No user {opts['user']!r}.")
        text = Path(opts["file"]).read_text(encoding="utf-8-sig")
        adapter = ADAPTERS[opts["format"]]
        rows = list(adapter(text, opts["run"], parse_map(opts["map"]))) if opts["format"] != "generic" else list(adapter(text, opts["run"]))
        if not rows:
            raise CommandError("No rows found in the file.")
        version = DataCategory.objects.get(code="model_output").current_version
        sub = create_submission(version, rows, user, channel=Channel.CSV, note=opts["note"] or f"{opts['format']} import of {Path(opts['file']).name}")
        self.stdout.write(f"Submission #{sub.pk}: {sub.accepted_count} accepted, {sub.flagged_count} flagged, {sub.rejected_count} rejected → {sub.get_status_display()}")
