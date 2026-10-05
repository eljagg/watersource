"""``manage.py bootstrap_workflows`` — seed the starting-point workflows described in the design plan.

Idempotent. WRA finalises stage names/roles in the initiation workshops (ToR H.viii).
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.accounts.models import Unit
from apps.accounts.ownership import STAGE_DEFAULTS
from apps.workflow.models import WorkflowDefinition, WorkflowStage

SEED = {
    "licence_application": {
        "name": "Licence application — four-stage approval",
        "stages": [
            ("intake", "Intake review", "reviewer", []),
            ("hydrogeology", "Technical assessment", "hydrologist", ["intake"]),
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


#: Standard licence conditions (design doc 14 §4). WRA edits the library in the admin console; these are starting points.
CONDITIONS = [
    ("general-volume", "Volume limit", "The licensee shall not abstract more than {volume} cubic metres per day from {source}.", "general", "both", True, 10),
    ("general-purpose", "Purpose", "Water abstracted under this licence shall be used only for the purpose stated in the application.", "general", "both", True, 20),
    ("metering-install", "Meter installation", "A water meter approved by the Authority shall be installed and maintained in good working order at the point of abstraction.", "metering", "both", True, 30),
    ("reporting-monthly", "Monthly returns", "The licensee shall submit monthly abstraction returns to the Authority through WaterSource by the 15th of the following month.", "reporting", "both", True, 40),
    ("monitoring-levels", "Water-level monitoring", "The licensee shall measure and record the static and pumping water level in the well at least once per month and submit the readings with the monthly return.", "monitoring", "well", False, 50),
    ("monitoring-quality", "Water-quality sampling", "The licensee shall have a water sample analysed by an approved laboratory at least once per year and submit the results to the Authority.", "monitoring", "both", False, 60),
    ("construction-standards", "Well construction", "The well shall be constructed, maintained and, when no longer required, decommissioned in accordance with the Authority's guidelines.", "construction", "well", False, 70),
    ("environmental-flow", "Environmental flow", "Abstraction shall cease when the flow at the Authority's reference gauge falls below the minimum flow notified to the licensee.", "environmental", "river", False, 80),
    ("general-access", "Access for inspection", "Officers of the Authority shall be given access to the abstraction point and the meter at all reasonable times.", "general", "both", True, 90),
    ("general-transfer", "Not transferable", "This licence is not transferable without the written consent of the Authority.", "general", "both", True, 100),
]


class Command(BaseCommand):
    """Create the default workflow definitions and the conditions library if absent."""
    help = "Create default workflow definitions and standard licence conditions (idempotent)."

    def handle(self, *args, **options):
        """Create definitions, stages, approver groups, return targets and conditions."""
        self._conditions()
        for code, spec in SEED.items():
            wd, created = WorkflowDefinition.objects.get_or_create(code=code, defaults={"name": spec["name"]})
            by_code = {}
            for order, (scode, name, group, _) in enumerate(spec["stages"], start=1):
                grp, _ = Group.objects.get_or_create(name=group)
                st, made = WorkflowStage.objects.get_or_create(definition=wd, code=scode, defaults={"order": order, "name": name, "approver_group": grp})
                if not made and scode == "hydrogeology" and st.name == "Hydrogeology review":  # renamed in v0.5.0; keep WRA's own later edits
                    st.name, st.approver_group = name, grp
                    st.instructions = "Record the technical assessment (WMU balance, impact, recommended volume and conditions) before approving."
                    st.save(update_fields=["name", "approver_group", "instructions"])
                if code == "licence_application" and st.owning_unit_id is None and scode in STAGE_DEFAULTS:  # v0.6.0: ownership by unit; WRA may change it in the admin
                    st.owning_unit = Unit.objects.filter(code=STAGE_DEFAULTS[scode]).first()
                    if st.owning_unit is not None:
                        st.save(update_fields=["owning_unit"])
                by_code[scode] = st
            for scode, _, _, returns in spec["stages"]:
                by_code[scode].can_return_to.set([by_code[r] for r in returns])
            self.stdout.write(f"{'created' if created else 'exists '} {code}")

    def _conditions(self):
        """Seed the standard conditions library (never overwrites edited rows)."""
        from apps.lic.models import LicenceCondition

        for code, title, text, category, applies, default, order in CONDITIONS:
            _, created = LicenceCondition.objects.get_or_create(code=code, defaults=dict(title=title, text=text, category=category, applies_to=applies, is_default=default, order=order))
            if created:
                self.stdout.write(f"created condition {code}")
