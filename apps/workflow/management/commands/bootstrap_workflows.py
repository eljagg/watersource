"""Seed the starting-point workflows described in the design plan. Idempotent.
WRA finalises stage names/roles in the initiation workshops (ToR H.viii)."""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.workflow.models import WorkflowDefinition, WorkflowStage

SEED = {
    "licence_application": {
        "name": "Licence application — four-stage approval",
        "stages": [
            ("intake", "Intake review", "reviewer", []),
            ("hydrogeology", "Hydrogeology review", "reviewer", ["intake"]),
            ("licensing_officer", "Licensing officer", "approver", ["intake", "hydrogeology"]),
            ("director", "Director approval", "approver", ["licensing_officer"]),
        ],
    },
    "data_submission_default": {
        "name": "Data submission — two-stage review",
        "stages": [
            ("review", "Data review", "reviewer", []),
            ("approve", "Approval and classification", "approver", ["review"]),
        ],
    },
    "correction": {
        "name": "Correction to approved data",
        "stages": [
            ("review", "Correction review", "reviewer", []),
            ("approve", "Correction approval", "approver", ["review"]),
        ],
    },
}


class Command(BaseCommand):
    help = "Create default workflow definitions (idempotent)."

    def handle(self, *args, **options):
        for code, spec in SEED.items():
            wd, created = WorkflowDefinition.objects.get_or_create(code=code, defaults={"name": spec["name"]})
            by_code = {}
            for order, (scode, name, group, _) in enumerate(spec["stages"], start=1):
                grp, _ = Group.objects.get_or_create(name=group)
                st, _ = WorkflowStage.objects.get_or_create(definition=wd, code=scode, defaults={"order": order, "name": name, "approver_group": grp})
                by_code[scode] = st
            for scode, _, _, returns in spec["stages"]:
                by_code[scode].can_return_to.set([by_code[r] for r in returns])
            self.stdout.write(f"{'created' if created else 'exists '} {code}")
