"""Licence Application Processing (ToR §C item 14, §G.1).

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
    """Source the licence draws from."""
    RIVER = "river", "River"
    SPRING = "spring", "Spring"
    WELL = "well", "Well"


class ApplicationStatus(models.TextChoices):
    """Application life-cycle (ToR G.1.iv)."""
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under review"
    INFO_REQUESTED = "info_requested", "Information requested"
    GRANTED = "granted", "Granted"
    REFUSED = "refused", "Not granted"
    WITHDRAWN = "withdrawn", "Withdrawn"


class ApplicationKind(models.TextChoices):
    """New, renewal or variation."""
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
        """Next value for ``key`` this year, formatted ``PREFIX-YYYY-NNNNNN``."""
        year = timezone.now().year
        with transaction.atomic():
            row, _ = cls.objects.select_for_update().get_or_create(key=key, year=year)
            row.value += 1
            row.save(update_fields=["value"])
        return f"{prefix}-{year}-{row.value:06d}"


class LicenceApplication(AuditedModel):
    """A water abstraction licence application (item 14) — the workflow subject."""
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
    wmu = models.ForeignKey("ref.WMU", null=True, blank=True, on_delete=models.PROTECT, related_name="applications", verbose_name="Watershed management unit",
                            help_text="Set by the technical assessment (defaults to the well's WMU).")
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
        """Assign the reference number on first save."""
        if not self.reference:
            self.reference = Sequence.next("application", settings.WATERSOURCE["APPLICATION_REF_PREFIX"])
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Applicant-facing detail page."""
        return reverse("lic:application_detail", args=[self.reference])

    @property
    def workflow(self):
        """The workflow instance for this application, if started."""
        from apps.workflow.engine import instance_for

        return instance_for(self)

    @property
    def owning_unit(self):
        """The WRA unit that owns licence applications (Permits & Licences Unit; ``accounts.ownership.FAMILIES``)."""
        from apps.accounts.models import Unit
        from apps.accounts.ownership import unit_code_for_model

        return Unit.objects.filter(code=unit_code_for_model("lic.LicenceApplication")).first()

    # -- workflow hooks --------------------------------------------------------
    def workflow_can_advance(self, instance, actor):
        """Block the technical-assessment stage until the assessment is recorded (design doc 14 §4)."""
        stage = instance.current_stage
        if stage is not None and stage.code in ASSESSMENT_STAGE_CODES and not hasattr(self, "assessment"):
            return "Complete the technical assessment before approving this stage."
        return None

    def on_workflow_approved(self, instance, actor, **meta):
        """Final-approval hook: mark granted and issue the licence (volume and conditions default from the assessment)."""
        assessment = getattr(self, "assessment", None)
        granted = meta.get("daily_volume_granted_m3") or (assessment.recommended_daily_volume_m3 if assessment else None) \
            or self.daily_volume_granted_m3 or self.daily_volume_requested_m3
        years = int(meta.get("term_years") or 1)
        self.daily_volume_granted_m3 = granted
        self.status = ApplicationStatus.GRANTED
        self.decided_at = timezone.now()
        self.decision_remarks = meta.get("comment", "")
        self.save()
        lic = Licence.issue(self, granted, years, actor, conditions=assessment.condition_texts() if assessment else [])
        if self.renewal_of_id:
            self.renewal_of.status = LicenceStatus.RENEWED
            self.renewal_of.save(update_fields=["status", "updated_at"])
        return lic

    def on_workflow_rejected(self, instance, actor, comment):
        """Rejection hook: mark refused with the decision remarks."""
        self.status = ApplicationStatus.REFUSED
        self.decided_at = timezone.now()
        self.decision_remarks = comment
        self.save(update_fields=["status", "decided_at", "decision_remarks", "updated_at"])

    def on_workflow_info_requested(self, instance, actor, comment):
        """Info-requested hook: park the application until the applicant resubmits."""
        self.status = ApplicationStatus.INFO_REQUESTED
        self.save(update_fields=["status", "updated_at"])


class DocumentKind(models.TextChoices):
    """Kinds of supporting document."""
    ID = "id", "Proof of identification"
    DRILLING_PERMIT = "drilling_permit", "Well drilling permit"
    SITE_PLAN = "site_plan", "Site plan"
    OTHER = "other", "Other supporting document"


class ScanStatus(models.TextChoices):
    """Malware scan outcome for an upload."""
    PENDING = "pending", "Pending scan"
    CLEAN = "clean", "Clean"
    INFECTED = "infected", "Infected — quarantined"
    SKIPPED = "skipped", "Scanner not configured"


class ApplicationDocument(AuditedModel):
    """A supporting document uploaded with an application (archived to DSpace)."""
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
    """Licence life-cycle."""
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    RENEWED = "renewed", "Renewed (superseded)"
    REVOKED = "revoked", "Revoked"
    SUSPENDED = "suspended", "Suspended"


class Licence(AuditedModel):
    """An issued abstraction licence (item 14.xii–xviii)."""
    number = models.CharField(max_length=32, unique=True, editable=False)
    application = models.OneToOneField(LicenceApplication, on_delete=models.PROTECT, related_name="licence")
    licensee = models.ForeignKey("ref.Party", on_delete=models.PROTECT, related_name="licences")
    parish = models.ForeignKey("ref.Parish", on_delete=models.PROTECT, related_name="licences")
    water_source = models.CharField(max_length=8, choices=WaterSource.choices)
    source_name = models.CharField(max_length=150)
    well = models.ForeignKey("ref.Well", null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    daily_volume_granted_m3 = models.DecimalField(max_digits=14, decimal_places=3)
    wmu = models.ForeignKey("ref.WMU", null=True, blank=True, on_delete=models.PROTECT, related_name="licences")
    conditions = models.JSONField(default=list, blank=True, help_text="Licence conditions as issued (text snapshot from the conditions library).")
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
        """Licence detail page."""
        return reverse("lic:licence_detail", args=[self.number])

    @property
    def days_to_expiry(self) -> int:
        """Days until expiry (negative once expired)."""
        return (self.expires_on - date.today()).days

    @classmethod
    def issue(cls, application: LicenceApplication, granted, years: int, actor, conditions: list | None = None):
        """Issue a licence for a granted application (with its conditions) and flag its well as licensed."""
        from dateutil.relativedelta import relativedelta

        today = date.today()
        lic = cls.objects.create(
            number=Sequence.next("licence", settings.WATERSOURCE["LICENCE_NO_PREFIX"]),
            application=application, licensee=application.applicant, parish=application.parish,
            water_source=application.water_source, source_name=application.source_name, well=application.well,
            daily_volume_granted_m3=granted, purpose=application.purpose, issued_on=today, wmu=application.wmu,
            expires_on=today + relativedelta(years=years), issued_by=actor if getattr(actor, "is_authenticated", False) else None,
            conditions=conditions or [],
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


# ---------------------------------------------------------------------------
# Technical assessment and the conditions library (design doc 14 §4; Permits & Licences + Planning & Investigation)
# ---------------------------------------------------------------------------
#: Workflow stage codes at which the technical assessment must exist before the item may advance.
ASSESSMENT_STAGE_CODES = ("hydrogeology", "technical_assessment")


class ConditionCategory(models.TextChoices):
    """Grouping of standard licence conditions."""

    GENERAL = "general", "General"
    METERING = "metering", "Metering and measurement"
    REPORTING = "reporting", "Reporting of abstraction"
    MONITORING = "monitoring", "Monitoring (levels, quality)"
    ENVIRONMENTAL = "environmental", "Environmental protection"
    CONSTRUCTION = "construction", "Well construction and maintenance"


class LicenceCondition(TimeStampedModel):
    """A standard condition WRA attaches to licences; the hydrologist picks from this library at assessment."""

    code = models.SlugField(max_length=32, unique=True)
    title = models.CharField(max_length=150)
    text = models.TextField(help_text="Wording as it appears on the licence. {volume} is replaced with the granted daily volume, {source} with the source name.")
    category = models.CharField(max_length=16, choices=ConditionCategory.choices, default=ConditionCategory.GENERAL)
    applies_to = models.CharField(max_length=8, choices=[("both", "Surface and ground water"), *WaterSource.choices], default="both")
    is_default = models.BooleanField(default=False, help_text="Pre-selected on every new assessment.")
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=100)

    class Meta:
        ordering = ["order", "code"]

    def __str__(self):
        return f"{self.code} — {self.title}"

    def render(self, application: LicenceApplication, volume) -> str:
        """Condition text with placeholders filled."""
        return self.text.replace("{volume}", f"{volume:,.0f}" if volume is not None else "the granted").replace("{source}", application.source_name)


class ImpactLevel(models.TextChoices):
    """Expected impact of the abstraction on existing users and the resource."""

    NONE = "none", "None expected"
    LOW = "low", "Low"
    MODERATE = "moderate", "Moderate — conditions required"
    HIGH = "high", "High — refuse or reduce"


class Recommendation(models.TextChoices):
    """Hydrologist's recommendation to the licensing officer."""

    GRANT = "grant", "Grant as requested"
    GRANT_REDUCED = "grant_reduced", "Grant at a reduced volume"
    MORE_INFO = "more_info", "Request further information / pump test"
    REFUSE = "refuse", "Refuse"


class TechnicalAssessment(AuditedModel):
    """The hydrologist's assessment of an application against the WMU balance (design doc 14 §4).

    One per application; required before the technical-assessment stage can be
    approved. Its recommended volume and conditions become the defaults the
    licensing officer sees at final approval and are snapshotted onto the licence.
    """

    application = models.OneToOneField(LicenceApplication, on_delete=models.CASCADE, related_name="assessment")
    assessed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="assessments")
    assessed_at = models.DateTimeField(default=timezone.now)
    wmu = models.ForeignKey("ref.WMU", null=True, blank=True, on_delete=models.PROTECT, related_name="assessments", verbose_name="Watershed management unit")
    aquifer = models.ForeignKey("ref.Aquifer", null=True, blank=True, on_delete=models.PROTECT, related_name="assessments")
    wmu_safe_yield_m3_d = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True, help_text="Snapshot at assessment time.")
    wmu_allocated_m3_d = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True, help_text="Active licences in the WMU at assessment time (snapshot).")
    wmu_reported_m3_d = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True, help_text="Average reported abstraction, last 12 months (snapshot).")
    impact = models.CharField(max_length=10, choices=ImpactLevel.choices, default=ImpactLevel.LOW)
    recommendation = models.CharField(max_length=14, choices=Recommendation.choices, default=Recommendation.GRANT)
    recommended_daily_volume_m3 = models.DecimalField("Recommended daily volume (m³)", max_digits=14, decimal_places=3, null=True, blank=True)
    conditions = models.ManyToManyField(LicenceCondition, blank=True, related_name="assessments")
    extra_conditions = models.TextField(blank=True, help_text="Additional conditions specific to this licence, one per line.")
    findings = models.TextField(help_text="Source reliability, nearby users, water-quality concerns, pump-test results.")

    class Meta:
        verbose_name = "technical assessment"

    def __str__(self):
        return f"Assessment of {self.application.reference}"

    @property
    def wmu_utilisation_after_pct(self):
        """Share of safe yield allocated if the recommended volume were granted."""
        if not self.wmu_safe_yield_m3_d:
            return None
        vol = self.recommended_daily_volume_m3 or self.application.daily_volume_requested_m3
        return round(float((self.wmu_allocated_m3_d or 0) + vol) / float(self.wmu_safe_yield_m3_d) * 100, 1)

    def condition_texts(self) -> list[str]:
        """Rendered standard conditions plus the free-text ones."""
        vol = self.recommended_daily_volume_m3 or self.application.daily_volume_requested_m3
        out = [c.render(self.application, vol) for c in self.conditions.filter(is_active=True)]
        out += [ln.strip() for ln in self.extra_conditions.splitlines() if ln.strip()]
        return out
