"""Observations and submitted data (ToR §C items 3, 6, 10, 13; design doc 14 §3).

These are the typed target tables the Data Submission application promotes
approved rows into (apps.submissions.promotion) and that WRA staff enter
directly. Every observation carries the quality columns from
``core.QualityMixin`` (grade, qualifiers) on top of the approval state and
classification every published record has, so the same row can be "working",
"in review" or "approved" whether it came from a client, a technician or a
migration load.

Time-series tables carry composite indexes on (site, timestamp); yearly
partitioning with pg_partman is applied by the DBA runbook once a table passes
~20 M rows (docs/database.md).
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from apps.core.models import PublishableModel, PublishedQuerySet, QualityMixin
from apps.ref.models import Spring, StreamflowStation, Well


class WellState(models.TextChoices):
    """Whether the well was pumping when the level was read (affects the reading)."""

    PUMPING = "pumping", "Pumping"
    NON_PUMPING = "non_pumping", "Non-pumping"


class WellWaterLevel(QualityMixin, PublishableModel):
    """Item 3 — well water level over time (metres below measuring point)."""

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


class StationReading(QualityMixin, PublishableModel):
    """Item 13 — streamflow station stage (and derived discharge) over time."""

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
    """Surface or groundwater abstraction (item 6)."""

    SURFACE = "surface", "Surface water"
    GROUND = "ground", "Underground water"


class AbstractionRecord(QualityMixin, PublishableModel):
    """Item 6 — water abstraction over time, compared to the licence's daily grant.

    ``over_limit`` is computed at promotion (apps.submissions.promotion) and raises
    the over-abstraction alert (ToR H.2.v, item 6.vii).
    """

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
        """Length of the reporting period in days (never less than one)."""
        return max((self.period_end - self.period_start).total_seconds() / 86400.0, 1.0)


class SampleSource(models.TextChoices):
    """Where a water-quality sample was taken (item 10 'Source')."""

    WELL = "well", "Well"
    SPRING = "spring", "Spring"
    STREAM = "stream", "Stream"


class WaterQualitySample(QualityMixin, PublishableModel):
    """Item 10 — water quality.

    Parameters are typed columns because the list is fixed by the ToR; extra
    parameters WRA defines later go to ``extra`` (JSONB) until promoted to a
    column in a release.
    """

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
        """The well, spring or station the sample was taken from."""
        return self.well or self.spring or self.station


class HistoryMethod(models.TextChoices):
    """Why an approved value changed (design doc 14 §3.2 — provenance of edits)."""

    CORRECTION = "correction", "Correction of an error"
    GAP_FILL = "gap_fill", "Gap fill (estimated value inserted)"
    ESTIMATE = "estimate", "Re-estimate of an existing value"
    SHIFT = "shift", "Datum / reference-point shift"
    REGRADE = "regrade", "Grade or qualifier change only"


class RecordHistory(models.Model):
    """Correction history for approved records (ToR H.xvii–xxi).

    Stores original values, corrected values, method, reason, corrector, approver
    and timestamps. Written by the promotion service (and by the hydrologist
    tools) inside the approval transaction. Append-only.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64, db_index=True)
    target = GenericForeignKey("content_type", "object_id")
    old_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    method = models.CharField(max_length=12, choices=HistoryMethod.choices, default=HistoryMethod.CORRECTION)
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
        """Refuse deletion: the table is append-only (second line after the DB grants)."""
        raise RuntimeError("RecordHistory is append-only")


class SeriesKind(models.TextChoices):
    """Which observation series an approval period covers."""

    WELL_LEVEL = "well_level", "Well water level"
    STATION_STAGE = "station_stage", "Station stage / discharge"
    ABSTRACTION = "abstraction", "Abstraction"
    WATER_QUALITY = "water_quality", "Water quality"


class ApprovalPeriod(models.Model):
    """A block of time over which a site's series was approved as a whole (design doc 14 §3.2).

    Hydrologists approve data in periods (typically a month or a water year), not
    row by row. Recording the period lets the dashboards and exports show where
    the approved record ends, and lets a later re-opening be traced. The rows
    inside the period are flipped to ``approved`` by ``services.approve_period``
    in the same transaction.
    """

    series = models.CharField(max_length=16, choices=SeriesKind.choices, db_index=True)
    well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.CASCADE, related_name="approval_periods")
    station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.CASCADE, related_name="approval_periods")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="approval_periods")
    approved_at = models.DateTimeField(auto_now_add=True)
    rows_approved = models.PositiveIntegerField(default=0)
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-starts_at"]
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="ck_approval_period_order"),
            models.CheckConstraint(condition=models.Q(well__isnull=False) | models.Q(station__isnull=False), name="ck_approval_period_site"),
        ]

    def __str__(self):
        return f"{self.get_series_display()} {self.site} {self.starts_at:%Y-%m-%d}–{self.ends_at:%Y-%m-%d}"

    @property
    def site(self):
        """The well or station the period belongs to."""
        return self.well or self.station


# ---------------------------------------------------------------------------
# Model output (design doc 15 §3.1) — results of SWAT+, Wflow, PRMS or any other model
# ---------------------------------------------------------------------------
class ModelRun(models.Model):
    """One run of an external hydrological model: which model, which scenario, how well it was calibrated.

    WaterSource is model-agnostic (design doc 15): it exports the observed record
    the models consume and keeps their results here, as a provisional data
    category distinct from observations, so simulated and measured series can be
    compared on the same dashboards without ever being confused.
    """

    code = models.SlugField(max_length=64, unique=True, help_text="Short identifier used in CSV uploads, e.g. riocobre-swatplus-2026a.")
    name = models.CharField(max_length=150)
    model_name = models.CharField("Model and version", max_length=80, help_text="e.g. SWAT+ rev. 62, Wflow.jl 1.0.4, PRMS 6.0")
    scenario = models.CharField(max_length=120, blank=True, help_text="Baseline, climate scenario, abstraction scenario…")
    basin = models.ForeignKey("ref.Basin", null=True, blank=True, on_delete=models.SET_NULL, related_name="model_runs")
    wmu = models.ForeignKey("ref.WMU", null=True, blank=True, on_delete=models.SET_NULL, related_name="model_runs")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    time_step = models.CharField(max_length=16, default="daily", help_text="daily, hourly, monthly")
    config_hash = models.CharField(max_length=64, blank=True, help_text="Hash of the model configuration (TOML / project folder) for reproducibility.")
    calibration_nse = models.DecimalField("Nash–Sutcliffe efficiency", max_digits=6, decimal_places=3, null=True, blank=True)
    calibration_kge = models.DecimalField("Kling–Gupta efficiency", max_digits=6, decimal_places=3, null=True, blank=True)
    calibration_station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.SET_NULL, related_name="calibration_runs",
                                            help_text="Gauge the metrics were computed against.")
    run_by = models.CharField(max_length=150, blank=True)
    run_at = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Karst treatment, forcing data used, known limitations.")
    is_active = models.BooleanField(default=True, help_text="Inactive runs are kept but hidden from dashboards.")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "model run"

    def __str__(self):
        return f"{self.name} ({self.model_name})"


class ModelVariable(models.TextChoices):
    """What a simulated value represents."""

    DISCHARGE = "discharge_m3_s", "Discharge (m³/s)"
    WATER_LEVEL = "water_level_m", "Water level (m)"
    RECHARGE = "recharge_mm", "Groundwater recharge (mm)"
    ACTUAL_ET = "actual_et_mm", "Actual evapotranspiration (mm)"
    SOIL_MOISTURE = "soil_moisture_mm", "Soil moisture (mm)"
    PRECIPITATION = "precipitation_mm", "Precipitation (mm)"
    BASEFLOW = "baseflow_m3_s", "Baseflow (m³/s)"
    OTHER = "other", "Other (see unit)"


class ModelFeature(models.TextChoices):
    """The model element a value belongs to."""

    STATION = "station", "Gauged station"
    WELL = "well", "Well"
    REACH = "reach", "Model reach / channel"
    SUBBASIN = "subbasin", "Subbasin / HRU"


class ModelOutput(QualityMixin, PublishableModel):
    """One simulated value: run × feature × variable × time (design doc 15 §3.1).

    Values are provisional by default (``approval_state`` is set by the review
    workflow like any other submission) and carry the run's classification.
    Rows linked to a station or well can be overlaid on that site's observed record.
    """

    run = models.ForeignKey(ModelRun, on_delete=models.CASCADE, related_name="outputs")
    feature_type = models.CharField(max_length=10, choices=ModelFeature.choices, default=ModelFeature.STATION)
    station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.PROTECT, related_name="model_outputs")
    well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.PROTECT, related_name="model_outputs")
    feature_ref = models.CharField(max_length=64, blank=True, help_text="Model's own id for the reach, subbasin or HRU (e.g. SWAT+ channel 12).")
    variable = models.CharField(max_length=24, choices=ModelVariable.choices, db_index=True)
    observed_at = models.DateTimeField("Simulated for", db_index=True)
    value = models.DecimalField(max_digits=14, decimal_places=4)
    unit = models.CharField(max_length=16, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["-observed_at"]
        verbose_name = "model output value"
        indexes = [models.Index(fields=["run", "variable", "observed_at"]), models.Index(fields=["station", "variable", "observed_at"])]
        constraints = [models.UniqueConstraint(fields=["run", "feature_type", "station", "well", "feature_ref", "variable", "observed_at"], name="uq_model_output_point")]

    def __str__(self):
        return f"{self.run.code} {self.variable} {self.observed_at:%Y-%m-%d}"
