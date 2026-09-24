"""
Licence Application Processing (ToR §C item 14, §G.1).

LicenceApplication is the workflow subject; on final approval the hook issues a
Licence with expiry, and the nightly task raises approaching-expiry / expired
alerts (item 14.xvii–xviii, G.1.viii).
"""
from datetime import date

from django.conf import settings
from django.db import models, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import AuditedModel, Classification, TimeStampedModel


class WaterSource(models.TextChoices):
    RIVER = "river", "River"
    SPRING = "spring", "Spring"
    WELL = "well", "Well"


class ApplicationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under review"
    INFO_REQUESTED = "info_requested", "Information requested"
    GRANTED = "granted", "Granted"
    REFUSED = "refused", "Not granted"
    WITHDRAWN = "withdrawn", "Withdrawn"


class ApplicationKind(models.TextChoices):
    NEW = "new", "New licence"
    RENEWAL = "renewal", "Renewal"
    VARIATION = "variation", "Variation of an existing licence"


class Sequence(models.Model):
    """Gap-free yearly sequences for application references and licence numbers."""

    key = models.CharField(max_length=32)
    year = models.PositiveIntegerField()
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["key", "year"], name="uq_sequence_key_year")]

    def __str__(self):
        return f"{self.key}/{self.year}={self.value}"

    @classmethod
    def next(cls, key: str, prefix: str) -> str:
        year = timezone.now().year
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(key=key, year=year)
            row.value += 1
            row.save(update_fields=["value"])
        return f"{prefix}-{year}-{row.value:06d}"


class LicenceApplication(AuditedModel):
    reference = models.CharField(max_length=32, unique=True, editable=False)
    kind = models.CharField(max_length=12, choices=ApplicationKind.choices, default=ApplicationKind.NEW)
    applicant_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="licence_applications")
    applicant = models.ForeignKey("ref.Party", on_delete=models.PROTECT, related_name="applications")
    # item 14 fields (name/address/email/phone live on Party; copied at submission for the record)
    applicant_name = models.CharField(max_length=200)
    applicant_address = models.TextField()
    applicant_email = models.EmailField()
    applicant_phone = models.CharField(max_length=32)
    parish = models.ForeignKey("ref.Parish", on_delete=models.PROTECT, related_name="applications")
    water_source = models.CharField(max_length=8, choices=WaterSource.choices)
    source_name = models.CharField("Name of source", max_length=150)
    well = models.ForeignKey("ref.Well", null=True, blank=True, on_delete=models.PROTECT, related_name="applications")
    daily_volume_requested_m3 = models.DecimalField(max_digits=14, decimal_places=3)
    daily_volume_granted_m3 = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    purpose = models.TextField("Purpose for which water will be used")
    status = models.CharField(max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_remarks = models.TextField(blank=True)
    renewal_of = models.ForeignKey("Licence", null=True, blank=True, on_delete=models.SET_NULL, related_name="renewal_applications")
    classification = models.CharField(max_length=16, choices=Classification.choices, default=Classification.STAFF_ONLY)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "parish"]), models.Index(fields=["water_source", "status"])]

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = Sequence.next("application", settings.WATERSOURCE["APPLICATION_REF_PREFIX"])
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("lic:application_detail", args=[self.reference])

    @property
    def workflow(self):
        from apps.workflow.engine import instance_for

        return instance_for(self)

    # -- workflow hooks --------------------------------------------------------
    def on_workflow_approved(self, instance, actor, **meta):
        granted = meta.get("daily_volume_granted_m3") or self.daily_volume_granted_m3 or self.daily_volume_requested_m3
        years = int(meta.get("term_years") or 1)
        self.daily_volume_granted_m3 = granted
        self.status = ApplicationStatus.GRANTED
        self.decided_at = timezone.now()
        self.decision_remarks = meta.get("comment", "")
        self.save()
        lic = Licence.issue(self, granted, years, actor)
        if self.renewal_of_id:
            self.renewal_of.status = LicenceStatus.RENEWED
            self.renewal_of.save(update_fields=["status", "updated_at"])
        return lic

    def on_workflow_rejected(self, instance, actor, comment):
        self.status = ApplicationStatus.REFUSED
        self.decided_at = timezone.now()
        self.decision_remarks = comment
        self.save(update_fields=["status", "decided_at", "decision_remarks", "updated_at"])

    def on_workflow_info_requested(self, instance, actor, comment):
        self.status = ApplicationStatus.INFO_REQUESTED
        self.save(update_fields=["status", "updated_at"])


class DocumentKind(models.TextChoices):
    ID = "id", "Proof of identification"
    DRILLING_PERMIT = "drilling_permit", "Well drilling permit"
    SITE_PLAN = "site_plan", "Site plan"
    OTHER = "other", "Other supporting document"


class ScanStatus(models.TextChoices):
    PENDING = "pending", "Pending scan"
    CLEAN = "clean", "Clean"
    INFECTED = "infected", "Infected — quarantined"
    SKIPPED = "skipped", "Scanner not configured"


class ApplicationDocument(AuditedModel):
    application = models.ForeignKey(LicenceApplication, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=16, choices=DocumentKind.choices, default=DocumentKind.OTHER)
    file = models.FileField(upload_to="applications/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    scan_status = models.CharField(max_length=10, choices=ScanStatus.choices, default=ScanStatus.PENDING)
    dspace_handle = models.CharField(max_length=100, blank=True, help_text="Handle of the DSpace item holding this file (ToR G.1.iii)")
    dspace_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.original_name


class LicenceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    RENEWED = "renewed", "Renewed (superseded)"
    REVOKED = "revoked", "Revoked"
    SUSPENDED = "suspended", "Suspended"


class Licence(AuditedModel):
    number = models.CharField(max_length=32, unique=True, editable=False)
    application = models.OneToOneField(LicenceApplication, on_delete=models.PROTECT, related_name="licence")
    licensee = models.ForeignKey("ref.Party", on_delete=models.PROTECT, related_name="licences")
    parish = models.ForeignKey("ref.Parish", on_delete=models.PROTECT, related_name="licences")
    water_source = models.CharField(max_length=8, choices=WaterSource.choices)
    source_name = models.CharField(max_length=150)
    well = models.ForeignKey("ref.Well", null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    daily_volume_granted_m3 = models.DecimalField(max_digits=14, decimal_places=3)
    purpose = models.TextField()
    issued_on = models.DateField()
    expires_on = models.DateField(db_index=True)
    status = models.CharField(max_length=10, choices=LicenceStatus.choices, default=LicenceStatus.ACTIVE, db_index=True)
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    expiry_alerts_sent = models.JSONField(default=list, blank=True, help_text="Days-before values already alerted, e.g. [90, 30]")
    expired_alert_sent_at = models.DateTimeField(null=True, blank=True)
    classification = models.CharField(max_length=16, choices=Classification.choices, default=Classification.STAFF_ONLY)

    class Meta:
        ordering = ["-issued_on"]

    def __str__(self):
        return self.number

    def get_absolute_url(self):
        return reverse("lic:licence_detail", args=[self.number])

    @property
    def days_to_expiry(self) -> int:
        return (self.expires_on - date.today()).days

    @classmethod
    def issue(cls, application: LicenceApplication, granted, years: int, actor):
        from dateutil.relativedelta import relativedelta

        today = date.today()
        lic = cls.objects.create(
            number=Sequence.next("licence", settings.WATERSOURCE["LICENCE_NO_PREFIX"]),
            application=application, licensee=application.applicant, parish=application.parish,
            water_source=application.water_source, source_name=application.source_name, well=application.well,
            daily_volume_granted_m3=granted, purpose=application.purpose, issued_on=today,
            expires_on=today + relativedelta(years=years), issued_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        if application.well_id:
            application.well.is_licensed = True
            application.well.licence_number = lic.number
            application.well.save(update_fields=["is_licensed", "licence_number", "updated_at"])
        return lic


class TimeStampedNote(TimeStampedModel):
    """Internal staff notes on an application (not visible to the applicant)."""

    application = models.ForeignKey(LicenceApplication, on_delete=models.CASCADE, related_name="notes")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    text = models.TextField()
