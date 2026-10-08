"""Unit console models: the data-cleansing queue and adoption sign-offs (stakeholder model: Super Users 'adjudicate cleansing' and 'co-sign adoption measures at M17')."""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class IssueKind(models.TextChoices):
    """What the profiler or an import found."""

    DUPLICATE = "duplicate", "Duplicate rows or records"
    UNMATCHED = "unmatched", "Values that match no reference record"
    OUT_OF_RANGE = "out_of_range", "Values outside the plausible range"
    MIXED_TYPES = "mixed_types", "Column mixes numbers, text or dates"
    DATE_FORMATS = "date_formats", "Several date formats in one column"
    PLACEHOLDER = "placeholder", "Placeholder blanks (N/A, -, 999)"
    ENCODING = "encoding", "Encoding or structure problem"
    OTHER = "other", "Other"


class IssueStatus(models.TextChoices):
    """Open or resolved."""

    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class Decision(models.TextChoices):
    """How the owning unit's Super User settled it."""

    KEEP_EXISTING = "keep_existing", "Keep the existing record; discard the incoming value"
    USE_INCOMING = "use_incoming", "Use the incoming value; replace the existing record"
    MERGE = "merge", "Merge: keep both, reconcile the fields"
    MAP = "map", "Map the incoming value to an existing record"
    CORRECT = "correct", "Correct at source and re-load"
    REJECT = "reject", "Reject the rows; do not load"
    ACCEPT = "accept", "Accept as is; no action"


class CleansingIssue(TimeStampedModel):
    """One conflict found while profiling or loading legacy data, waiting for the owning unit's decision."""

    unit = models.ForeignKey("accounts.Unit", on_delete=models.PROTECT, related_name="cleansing_issues")
    kind = models.CharField(max_length=16, choices=IssueKind.choices, default=IssueKind.OTHER)
    source = models.CharField(max_length=200, help_text="File, sheet or import run the issue came from.")
    column = models.CharField(max_length=120, blank=True)
    summary = models.CharField(max_length=300)
    details = models.JSONField(default=dict, blank=True, help_text="Examples, unmatched values, candidate matches, counts.")
    rows_affected = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=IssueStatus.choices, default=IssueStatus.OPEN, db_index=True)
    decision = models.CharField(max_length=16, choices=Decision.choices, blank=True)
    decision_target = models.CharField(max_length=200, blank=True, help_text="For 'map': the reference record the value maps to.")
    decision_note = models.TextField(blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cleansing_decisions")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "-created_at"]
        verbose_name = "data-cleansing issue"

    def __str__(self):
        return f"{self.get_kind_display()} — {self.summary[:60]}"

    def resolve(self, user, decision: str, note: str = "", target: str = ""):
        """Record the Super User's decision and close the issue (audited)."""
        from apps.core.audit import log

        self.decision, self.decision_note, self.decision_target = decision, note, target
        self.decided_by, self.decided_at, self.status = user, timezone.now(), IssueStatus.RESOLVED
        self.save(update_fields=["decision", "decision_note", "decision_target", "decided_by", "decided_at", "status", "updated_at"])
        log("cleansing.resolved", target=self, summary=f"{self.unit.code}: {self.get_decision_display()} — {self.summary[:80]}", actor=user)


ADOPTION_MEASURES = [
    ("trained", "All unit staff who use the system have completed training."),
    ("data_loaded", "The unit's data has been migrated, reconciled and signed off."),
    ("workflow_live", "Approvals for the unit's data run in WaterSource, not on paper or e-mail."),
    ("cleansing_cleared", "The unit's data-cleansing queue is empty or every open issue has an agreed plan."),
    ("support_known", "Unit staff know the Super User is first-line support and how to reach the ICT unit."),
]


class AdoptionSignoff(TimeStampedModel):
    """The Super User's confirmation that the unit has adopted the system (Work Plan M17); the latest one per unit is current."""

    unit = models.ForeignKey("accounts.Unit", on_delete=models.PROTECT, related_name="adoption_signoffs")
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="adoption_signoffs")
    signed_at = models.DateTimeField(default=timezone.now)
    measures = models.JSONField(default=dict, help_text="Measure code → true/false as confirmed.")
    statement = models.TextField(blank=True)

    class Meta:
        ordering = ["-signed_at"]
        verbose_name = "adoption sign-off"

    def __str__(self):
        return f"{self.unit.code} adoption — {self.signed_by} {self.signed_at:%d %b %Y}"

    @property
    def complete(self) -> bool:
        """True when every measure is confirmed."""
        return all(self.measures.get(code) for code, _ in ADOPTION_MEASURES)
