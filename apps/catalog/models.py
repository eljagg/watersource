"""
Configurable data category / template framework (ToR G.2.i–iii).

A DataCategory has immutable published CategoryVersions. Each version is a
list of CategoryFields plus CategoryRules. From one definition the system
generates: the web form, the CSV template, the JSON Schema for the API, and
the validation that runs on every channel (services.py). Old submissions
always validate against the version they were submitted under.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Classification, TimeStampedModel


class TargetModel(models.TextChoices):
    ABSTRACTION = "obs.AbstractionRecord", "Water abstraction record"
    WATER_QUALITY = "obs.WaterQualitySample", "Water quality sample"
    WELL_WATER_LEVEL = "obs.WellWaterLevel", "Well water level"
    STATION_READING = "obs.StationReading", "Streamflow station reading"
    GENERIC = "submissions.GenericRecord", "Generic (stored as submitted)"


class LinkKind(models.TextChoices):
    NONE = "none", "No site link"
    WELL = "well", "Well"
    STATION = "station", "Streamflow station"
    LICENCE = "licence", "Licence"
    SPRING = "spring", "Spring"


class DataCategory(TimeStampedModel):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    target_model = models.CharField(max_length=64, choices=TargetModel.choices, default=TargetModel.GENERIC)
    link_kind = models.CharField(max_length=16, choices=LinkKind.choices, default=LinkKind.NONE)
    workflow = models.ForeignKey("workflow.WorkflowDefinition", on_delete=models.PROTECT, related_name="categories")
    default_classification = models.CharField(max_length=16, choices=Classification.choices, default=Classification.STAFF_ONLY)
    submitter_groups = models.ManyToManyField("auth.Group", blank=True, help_text="Who may submit (empty = any verified client or staff).")
    allow_csv = models.BooleanField(default=True)
    allow_api = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "data categories"

    def __str__(self):
        return self.name

    @property
    def current_version(self):
        return self.versions.filter(status=VersionStatus.PUBLISHED).order_by("-version").first()


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    RETIRED = "retired", "Retired"


class CategoryVersion(TimeStampedModel):
    category = models.ForeignKey(DataCategory, on_delete=models.CASCADE, related_name="versions")
    version = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=VersionStatus.choices, default=VersionStatus.DRAFT)
    notes = models.TextField(blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    json_schema = models.JSONField(default=dict, blank=True, editable=False)

    class Meta:
        ordering = ["category", "-version"]
        constraints = [models.UniqueConstraint(fields=["category", "version"], name="uq_category_version")]

    def __str__(self):
        return f"{self.category.code} v{self.version}"

    @property
    def is_editable(self):
        return self.status == VersionStatus.DRAFT

    def publish(self, user=None):
        from .services import build_json_schema

        if self.status != VersionStatus.DRAFT:
            raise ValueError("Only drafts can be published.")
        if not self.fields.exists():
            raise ValueError("Add at least one field before publishing.")
        self.category.versions.filter(status=VersionStatus.PUBLISHED).update(status=VersionStatus.RETIRED)
        self.json_schema = build_json_schema(self)
        self.status = VersionStatus.PUBLISHED
        self.published_at = timezone.now()
        self.published_by = user
        self.save()

    def clone_as_draft(self):
        new = CategoryVersion.objects.create(category=self.category, version=self.category.versions.count() + 1)
        for f in self.fields.all():
            f.pk = None
            f.version = new
            f.save()
        for r in self.rules.all():
            r.pk = None
            r.version = new
            r.save()
        return new


class FieldType(models.TextChoices):
    INTEGER = "integer", "Whole number"
    DECIMAL = "decimal", "Decimal number"
    TEXT = "text", "Text"
    DATE = "date", "Date"
    DATETIME = "datetime", "Date and time"
    BOOLEAN = "boolean", "Yes/No"
    ENUM = "enum", "Choice from a list"
    WELL = "well", "Well (reference)"
    STATION = "station", "Streamflow station (reference)"
    LICENCE = "licence", "Licence number (reference)"
    SPRING = "spring", "Spring (reference)"


class CategoryField(models.Model):
    version = models.ForeignKey(CategoryVersion, on_delete=models.CASCADE, related_name="fields")
    order = models.PositiveSmallIntegerField(default=0)
    name = models.SlugField(max_length=64, help_text="Column name in CSV/API, e.g. abstraction_volume_m3")
    label = models.CharField(max_length=150)
    field_type = models.CharField(max_length=16, choices=FieldType.choices)
    unit = models.CharField(max_length=32, blank=True)
    required = models.BooleanField(default=True)
    min_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    max_value = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)
    regex = models.CharField(max_length=255, blank=True)
    choices = models.JSONField(default=list, blank=True, help_text='For enum: ["pumping", "non_pumping"]')
    help_text = models.CharField(max_length=255, blank=True)
    target_field = models.CharField(max_length=64, blank=True, help_text="Column on the target model this maps to (blank = keep in payload only).")
    soft_min = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True, help_text="Below this: flag for reviewer, do not block.")
    soft_max = models.DecimalField(max_digits=18, decimal_places=6, null=True, blank=True)

    class Meta:
        ordering = ["version", "order", "pk"]
        constraints = [models.UniqueConstraint(fields=["version", "name"], name="uq_field_name_per_version")]

    def __str__(self):
        return f"{self.version}.{self.name}"


class RuleType(models.TextChoices):
    DATE_ORDER = "date_order", "Date A must not be after date B"
    RANGE_PAIR = "range_pair", "Field A must be ≤ field B"
    SUM_OF_PARTS = "sum_of_parts", "Fields must sum to another field (± tolerance)"
    LICENCE_LIMIT = "licence_limit", "Abstraction volume vs licensed daily volume"
    REQUIRED_IF = "required_if", "Field required when another field has a value"
    UNIQUE_IN_BATCH = "unique_in_batch", "No two rows may share these fields"


class Severity(models.TextChoices):
    HARD = "hard", "Hard (blocks acceptance)"
    SOFT = "soft", "Soft (flag for reviewer)"


class CategoryRule(models.Model):
    version = models.ForeignKey(CategoryVersion, on_delete=models.CASCADE, related_name="rules")
    rule_type = models.CharField(max_length=24, choices=RuleType.choices)
    params = models.JSONField(default=dict, help_text='e.g. {"a": "period_start", "b": "period_end"}')
    severity = models.CharField(max_length=8, choices=Severity.choices, default=Severity.HARD)
    message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["version", "pk"]

    def __str__(self):
        return f"{self.version} {self.rule_type}"
