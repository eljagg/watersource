"""
Observations and submitted data (ToR §C items 3, 6, 10, 13).

These are the typed target tables the Data Submission application promotes
approved rows into (apps.submissions.promotion). Time-series tables carry
composite indexes on (site, timestamp); yearly partitioning with pg_partman is
applied by the DBA runbook once a table passes ~20 M rows (docs/database.md).
"""
from django.db import models

from apps.core.models import PublishableModel, PublishedQuerySet
from apps.ref.models import Spring, StreamflowStation, Well


class WellState(models.TextChoices):
    PUMPING = "pumping", "Pumping"
    NON_PUMPING = "non_pumping", "Non-pumping"


class WellWaterLevel(PublishableModel):
    """Item 3 — well water level over time."""

    well = models.ForeignKey(Well, on_delete=models.PROTECT, related_name="water_levels")
    measured_at = models.DateTimeField(db_index=True)
    water_level_m = models.DecimalField(max_digits=8, decimal_places=3)
    well_state = models.CharField(max_length=16, choices=WellState.choices, blank=True)
    measured_by = models.CharField(max_length=150, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-measured_at"]
        indexes = [models.Index(fields=["well", "measured_at"])]
        constraints = [models.UniqueConstraint(fields=["well", "measured_at"], name="uq_wwl_well_time")]


class StationReading(PublishableModel):
    """Item 13 — streamflow station water levels over time."""

    station = models.ForeignKey(StreamflowStation, on_delete=models.PROTECT, related_name="readings")
    read_at = models.DateTimeField(db_index=True)
    recorder_reading_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    observer_reading_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    discharge_m3_s = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-read_at"]
        indexes = [models.Index(fields=["station", "read_at"])]
        constraints = [models.UniqueConstraint(fields=["station", "read_at"], name="uq_reading_station_time")]


class AbstractionSource(models.TextChoices):
    SURFACE = "surface", "Surface water"
    GROUND = "ground", "Underground water"


class AbstractionRecord(PublishableModel):
    """Item 6 — water abstraction over time, compared to the licence's daily grant.
    over_limit is computed at promotion (apps.submissions.promotion) and raises the
    over-abstraction alert (ToR H.2.v, item 6.vii)."""

    licence = models.ForeignKey("lic.Licence", null=True, blank=True, on_delete=models.PROTECT, related_name="abstractions")
    well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.PROTECT, related_name="abstractions")
    station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.PROTECT, related_name="abstractions")
    source_type = models.CharField(max_length=8, choices=AbstractionSource.choices)
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField()
    abstraction_rate_m3_d = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    abstraction_volume_m3 = models.DecimalField(max_digits=16, decimal_places=3)
    daily_volume_granted_m3 = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    over_limit = models.BooleanField(default=False, db_index=True)
    over_limit_pct = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    meter_reading = models.DecimalField(max_digits=16, decimal_places=3, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-period_start"]
        indexes = [models.Index(fields=["licence", "period_start"]), models.Index(fields=["well", "period_start"])]
        constraints = [models.CheckConstraint(condition=models.Q(period_end__gte=models.F("period_start")), name="ck_abstraction_period")]

    @property
    def days(self) -> float:
        return max((self.period_end - self.period_start).total_seconds() / 86400.0, 1.0)


class SampleSource(models.TextChoices):
    WELL = "well", "Well"
    SPRING = "spring", "Spring"
    STREAM = "stream", "Stream"


class WaterQualitySample(PublishableModel):
    """Item 10 — water quality. Parameters are typed columns because the list is
    fixed by the ToR; extra parameters WRA defines later go to `extra` (JSONB)
    until promoted to a column in a release."""

    source_type = models.CharField(max_length=8, choices=SampleSource.choices)
    well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.PROTECT, related_name="water_quality")
    spring = models.ForeignKey(Spring, null=True, blank=True, on_delete=models.PROTECT, related_name="water_quality")
    station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.PROTECT, related_name="water_quality")
    laboratory = models.ForeignKey("ref.Party", null=True, blank=True, on_delete=models.SET_NULL, related_name="analysed_samples")
    sample_ref = models.CharField(max_length=64, blank=True, db_index=True)
    sampled_at = models.DateTimeField(db_index=True)
    analysed_at = models.DateTimeField(null=True, blank=True)
    sampled_by = models.CharField(max_length=150, blank=True)
    analysed_by = models.CharField(max_length=150, blank=True)
    sample_depth_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    specific_conductivity_us_cm = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    temperature_c = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    ph = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    colour = models.CharField(max_length=50, blank=True)
    odour = models.CharField(max_length=50, blank=True)
    turbidity_ntu = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    percent_sodium = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    sodium_adsorption_ratio = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    calcium_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    magnesium_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    potassium_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    sodium_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    carbonate_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    bicarbonate_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    sulphate_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    chloride_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    nitrate_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    hardness_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    alkalinity_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    total_dissolved_solids_mg_l = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-sampled_at"]
        indexes = [models.Index(fields=["well", "sampled_at"]), models.Index(fields=["station", "sampled_at"]), models.Index(fields=["spring", "sampled_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(source_type="well", well__isnull=False)
                    | models.Q(source_type="spring", spring__isnull=False)
                    | models.Q(source_type="stream", station__isnull=False)
                ),
                name="ck_wq_source_link",
            )
        ]

    @property
    def site(self):
        return self.well or self.spring or self.station


class RecordHistory(models.Model):
    """Correction history for approved records (ToR H.xvii–xxi): original values,
    corrected values, reason, corrector, approver and timestamps. Written by the
    promotion service inside the approval transaction. Append-only."""

    from django.contrib.contenttypes.fields import GenericForeignKey
    from django.contrib.contenttypes.models import ContentType

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64, db_index=True)
    target = GenericForeignKey("content_type", "object_id")
    old_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    reason = models.TextField()
    corrected_by = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="corrections_made")
    corrected_at = models.DateTimeField()
    approved_by = models.ForeignKey("accounts.User", null=True, on_delete=models.PROTECT, related_name="corrections_approved")
    approved_at = models.DateTimeField(null=True)
    submission = models.ForeignKey("submissions.Submission", null=True, blank=True, on_delete=models.SET_NULL, related_name="history_entries")

    class Meta:
        ordering = ["-approved_at"]
        verbose_name_plural = "record history"

    def __str__(self):
        return f"{self.content_type_id}:{self.object_id} corrected {self.corrected_at:%Y-%m-%d}"

    def delete(self, *args, **kwargs):
        raise RuntimeError("RecordHistory is append-only")
