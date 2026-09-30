"""``manage.py load_reference_data`` — seed lookups from ``data/reference/*.csv`` (idempotent).

Each CSV maps to one lookup model. Rows are matched on ``code`` and updated in
place, so the command can be re-run after WRA sends corrected lists (ToR §D
data migration — reference data first). Lines starting with ``#`` are comments.

Usage::

    python manage.py load_reference_data            # all files
    python manage.py load_reference_data parishes   # one file
    python manage.py load_reference_data --dir /path/to/wra/lists
"""
from __future__ import annotations

import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.ref.models import WMU, Basin, HydrostratUnit, Parish, Qualifier, River

#: file stem → (model, columns other than code, foreign keys {column: (model, key)})
LOADERS = {
    "parishes": (Parish, ["name"], {}),
    "basins": (Basin, ["name"], {}),
    "wmus": (WMU, ["name"], {"basin": (Basin, "basin")}),
    "hydrostrat_units": (HydrostratUnit, ["name", "kind"], {}),
    "rivers": (River, ["name"], {}),
    "qualifiers": (Qualifier, ["name", "description", "applies_to"], {}),
}
#: Load order matters for foreign keys.
ORDER = ["parishes", "basins", "wmus", "hydrostrat_units", "rivers", "qualifiers"]


def read_csv(path: Path) -> list[dict]:
    """Read a UTF-8 CSV, skipping blank and ``#`` comment lines."""
    with path.open(encoding="utf-8-sig") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    return list(csv.DictReader(lines))


class Command(BaseCommand):
    """Load or refresh the reference lookups from CSV."""

    help = "Load reference lookups (parishes, basins, WMUs, hydrostratigraphic units, rivers, qualifiers) from CSV. Idempotent."

    def add_arguments(self, parser):
        """Accept optional file stems and a directory override."""
        parser.add_argument("names", nargs="*", help=f"Subset of: {', '.join(ORDER)}")
        parser.add_argument("--dir", default=str(Path(settings.BASE_DIR) / "data" / "reference"), help="Directory holding the CSV files")

    @transaction.atomic
    def handle(self, *args, **options):
        """Load each requested file inside one transaction; report created/updated counts."""
        directory = Path(options["dir"])
        names = options["names"] or ORDER
        unknown = [n for n in names if n not in LOADERS]
        if unknown:
            raise CommandError(f"Unknown reference set(s): {', '.join(unknown)}. Choose from {', '.join(ORDER)}.")
        for name in ORDER:
            if name not in names:
                continue
            path = directory / f"{name}.csv"
            if not path.exists():
                self.stderr.write(f"skip    {name}: {path} not found")
                continue
            created, updated = self._load(name, read_csv(path))
            self.stdout.write(f"{name:18s} {created:4d} created {updated:4d} updated")

    def _load(self, name: str, rows: list[dict]) -> tuple[int, int]:
        model, columns, fks = LOADERS[name]
        created = updated = 0
        for row in rows:
            code = (row.get("code") or "").strip()
            if not code:
                raise CommandError(f"{name}: a row has no code: {row}")
            values = {c: (row.get(c) or "").strip() for c in columns}
            for column, (fk_model, key) in fks.items():
                ref = (row.get(column) or "").strip()
                values[key] = fk_model.objects.get(code=ref) if ref else None
            _, was_created = model.objects.update_or_create(code=code, defaults=values)
            created += was_created
            updated += not was_created
        return created, updated
