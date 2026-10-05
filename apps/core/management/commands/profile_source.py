"""``manage.py profile_source`` — profile legacy extracts and write the M3 Data Quality Assessment Report.

Example::

    manage.py profile_source "extracts/*.csv" extracts/wells.xlsx --out reports/m3 --title "WRA legacy data — DQA"

Writes ``<out>.md`` (report body, paste into the M3 document) and ``<out>.json``
(machine-readable, consumed by the migration toolkit in Sprint 4). Reference
matching uses the wells, stations, parishes, basins and licences already in
WaterSource; with ``--no-reference`` the command runs without a database.
"""
import glob
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.profiling import profile_file, reference_lookups, render_markdown, to_json


class Command(BaseCommand):
    """Profile one or more CSV/XLSX files."""

    help = "Profile legacy CSV/XLSX extracts and write the Data Quality Assessment Report (Markdown + JSON)."

    def add_arguments(self, parser):
        """CLI options."""
        parser.add_argument("files", nargs="+", help="Files or glob patterns (CSV, TSV, XLSX)")
        parser.add_argument("--out", default="data_quality_assessment", help="Output path without extension")
        parser.add_argument("--title", default="Data Quality Assessment Report (Milestone 3)")
        parser.add_argument("--no-reference", action="store_true", help="Skip matching against WaterSource reference tables")

    def handle(self, *args, **opts):
        """Run the profiler and write both outputs."""
        paths = []
        for pattern in opts["files"]:
            paths += [Path(p) for p in sorted(glob.glob(pattern))] or ([Path(pattern)] if Path(pattern).exists() else [])
        if not paths:
            raise CommandError("No input files found.")
        reference = {} if opts["no_reference"] else reference_lookups()
        profiles = []
        for p in paths:
            self.stdout.write(f"profiling {p} …")
            profiles.append(profile_file(p, reference))
        out = Path(opts["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.with_suffix(".md").write_text(render_markdown(profiles, opts["title"]), encoding="utf-8")
        out.with_suffix(".json").write_text(json.dumps(to_json(profiles), indent=2, default=str), encoding="utf-8")
        total_issues = sum(len(p.issues) for p in profiles)
        self.stdout.write(self.style.SUCCESS(f"{len(profiles)} file(s), {sum(p.rows for p in profiles):,} rows, {total_issues} finding(s) → {out.with_suffix('.md')} and {out.with_suffix('.json')}"))
