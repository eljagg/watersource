"""
Data Submission application (ToR §G.2).

Submission = the envelope (who, which category version, which channel, file).
SubmissionRecord = one validated row, kept as JSONB until final approval, then
promoted into the typed target table in one transaction that also stamps the
access classification (promotion.py). A Correction is a Submission whose
records point at existing approved rows; on approval the old and new values
are written to obs.RecordHistory (ToR H.xvii–xxi).
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse

from apps.core.models import AuditedModel, Classification, PublishableModel, PublishedQuerySet


class Channel(models.TextChoices):
    FORM = "form", "Web form"
    CSV = "csv", "CSV upload"
    API = "api", "API"


class SubmissionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    VALIDATING = "validating", "Validating"
    FAILED_VALIDATION = "failed", "Failed validation"
    UNDER_REVIEW = "under_review", "Under review"
    INFO_REQUESTED = "info_requested", "Information requested"
    APPROVED = "approved", "Approved and published"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


class Submission(AuditedModel):
    category_version = models.ForeignKey("catalog.CategoryVersion", on_delete=models.PROTECT, related_name="submissions")
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="submissions")
    party = models.ForeignKey("ref.Party", null=True, blank=True, on_delete=models.SET_NULL, related_name="submissions")
    channel = models.CharField(max_length=8, choices=Channel.choices, default=Channel.FORM)
    status = models.CharField(max_length=16, choices=SubmissionStatus.choices, default=SubmissionStatus.DRAFT, db_index=True)
    is_correction = models.BooleanField(default=False)
    correction_reason = models.TextField(blank=True)
    file = models.FileField(upload_to="submissions/%Y/%m/", blank=True)
    original_filename = models.CharField(max_length=255, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    accepted_count = models.PositiveIntegerField(default=0)
    flagged_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    classification = models.CharField(max_length=16, choices=Classification.choices, null=True, blank=True,
                                      help_text="Set by the approver at final approval (ToR G.2.vi).")
    submitter_note = models.TextField(blank=True)
    api_idempotency_key = models.CharField(max_length=64, blank=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "category_version"])]

    def __str__(self):
        return f"Submission #{self.pk} {self.category_version}"

    def get_absolute_url(self):
        return reverse("submissions:detail", args=[self.pk])

    @property
    def category(self):
        return self.category_version.category

    @property
    def workflow(self):
        from apps.workflow.engine import instance_for

        return instance_for(self)

    @property
    def summary(self):
        who = self.submitter.full_name if self.submitter_id else "system"
        return f"{self.category.name} · {self.row_count} row(s) · {who}"

    # -- workflow hooks --------------------------------------------------------
    def on_workflow_approved(self, instance, actor, **meta):
        from .promotion import promote

        classification = meta.get("classification") or self.category.default_classification
        promote(self, actor, classification)

    def on_workflow_rejected(self, instance, actor, comment):
        self.status = SubmissionStatus.REJECTED
        self.save(update_fields=["status", "updated_at"])

    def on_workflow_info_requested(self, instance, actor, comment):
        self.status = SubmissionStatus.INFO_REQUESTED
        self.save(update_fields=["status", "updated_at"])


class RecordStatus(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    FLAGGED = "flagged", "Flagged for review"
    REJECTED = "rejected", "Rejected by validation"
    PROMOTED = "promoted", "Promoted to consolidated database"


class SubmissionRecord(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="records")
    row_no = models.PositiveIntegerField()
    payload = models.JSONField(default=dict)
    errors = models.JSONField(default=dict, blank=True)
    flags = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=10, choices=RecordStatus.choices, default=RecordStatus.ACCEPTED)
    # for corrections: the approved record this row replaces
    target_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    target_object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")
    # after promotion: the row created/updated in the typed table
    promoted_content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    promoted_object_id = models.CharField(max_length=64, blank=True)
    promoted = GenericForeignKey("promoted_content_type", "promoted_object_id")

    class Meta:
        ordering = ["submission", "row_no"]
        constraints = [models.UniqueConstraint(fields=["submission", "row_no"], name="uq_record_row")]

    def __str__(self):
        return f"{self.submission_id}:{self.row_no}"


class GenericRecord(PublishableModel):
    """Target for categories WRA defines that have no typed table yet: the
    validated payload is stored as-is with its site link and classification."""

    category_version = models.ForeignKey("catalog.CategoryVersion", on_delete=models.PROTECT, related_name="generic_records")
    payload = models.JSONField(default=dict)
    well = models.ForeignKey("ref.Well", null=True, blank=True, on_delete=models.PROTECT, related_name="generic_records")
    station = models.ForeignKey("ref.StreamflowStation", null=True, blank=True, on_delete=models.PROTECT, related_name="generic_records")
    licence = models.ForeignKey("lic.Licence", null=True, blank=True, on_delete=models.PROTECT, related_name="generic_records")
    observed_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]


class ImportRun(models.Model):
    """Evidence trail for every bulk load (ToR data quality assurance)."""

    submission = models.ForeignKey(Submission, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="running")
    rows_in = models.PositiveIntegerField(default=0)
    rows_accepted = models.PositiveIntegerField(default=0)
    rows_flagged = models.PositiveIntegerField(default=0)
    rows_rejected = models.PositiveIntegerField(default=0)
    file_sha256 = models.CharField(max_length=64, blank=True)
    log = models.TextField(blank=True)

    def __str__(self):
        return f"ImportRun {self.pk} {self.status}"
