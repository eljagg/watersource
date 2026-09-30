"""Reference and hydrological master data (ToR §C items 1, 2, 4, 5, 7, 8, 9, 11, 12; design doc 14 §3.4).

Three families live here:

* **Lookups** — parish, basin, WMU, sub-WMU, hydrostratigraphic unit, river,
  observation qualifier. Seeded from ``data/reference/*.csv`` by
  ``manage.py load_reference_data``.
* **Sites** — wells (with lithology, casing, pump tests, ownership and status
  history), streamflow stations and springs.
* **Site master record** — instruments and where they are installed,
  reference-point history and the visit log, so a hydrologist can see the
  physical history of a site next to its data.

Geometry is stored in EPSG:3448 (JAD2001 / Jamaica Metric Grid) as supplied by
WRA; exports transform to EPSG:4326. Parish/basin/WMU are assigned by spatial
join at load time when the lookup polygons are present, otherwise taken from the
source record.
"""
from django.conf import settings
from django.contrib.gis.db import models as gis
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from apps.core.models import AuditedModel, PublishableModel, PublishedQuerySet

SRID = 3448


class CodedLookup(models.Model):
    """Base for code + name lookups, optionally with a boundary polygon."""

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    geom = gis.MultiPolygonField(srid=SRID, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Parish(CodedLookup):
    """One of Jamaica's fourteen parishes."""

    class Meta(CodedLookup.Meta):
        verbose_name_plural = "parishes"


class Basin(CodedLookup):
    """Hydrological basin."""


class WMU(CodedLookup):
    """Watershed management unit."""

    basin = models.ForeignKey(Basin, null=True, blank=True, on_delete=models.PROTECT, related_name="wmus")

    class Meta(CodedLookup.Meta):
        verbose_name = "watershed management unit"


class SubWMU(CodedLookup):
    """Sub-division of a watershed management unit."""

    wmu = models.ForeignKey(WMU, on_delete=models.PROTECT, related_name="sub_wmus")

    class Meta(CodedLookup.Meta):
        verbose_name = "sub-watershed management unit"


class HydrostratUnit(CodedLookup):
    """Aquifer, aquiclude or aquitard a well is completed in (item 2)."""

    KIND = [("aquifer", "Aquifer"), ("aquiclude", "Aquiclude"), ("aquitard", "Aquitard")]
    kind = models.CharField(max_length=16, choices=KIND, default="aquifer")

    class Meta(CodedLookup.Meta):
        verbose_name = "hydrostratigraphic unit"


class River(CodedLookup):
    """River a streamflow station sits on (item 11)."""


class Qualifier(models.Model):
    """Qualifier codes attached to observations (design doc 14 §3.2).

    Qualifiers say *why* a value should be read with care without changing the
    value itself — the well was pumping, the gauge was iced, the logger was
    replaced. The code is what ``obs.*.qualifiers`` stores.
    """

    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    applies_to = models.CharField(max_length=32, blank=True, help_text="Comma-separated series kinds, blank = all")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class PartyKind(models.TextChoices):
    """What role a party plays in WRA's records."""

    OWNER = "owner", "Well owner"
    DRILLER = "driller", "Driller"
    APPLICANT = "applicant", "Licence applicant"
    LABORATORY = "laboratory", "Laboratory"
    ABSTRACTOR = "abstractor", "Licensed abstractor"
    OTHER = "other", "Other"


class Party(AuditedModel):
    """Owners, drillers, applicants, laboratories — de-duplicated in migration.

    Personal data lives here and in lic.*; never in a public view (ToR I.v).
    """

    kind = models.CharField(max_length=16, choices=PartyKind.choices, default=PartyKind.OTHER)
    name = models.CharField(max_length=200, db_index=True)
    normalised_name = models.CharField(max_length=200, db_index=True, editable=False)
    address = models.TextField(blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)
    is_organisation = models.BooleanField(default=False)
    merged_into = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_from")
    legacy_ids = ArrayField(models.CharField(max_length=64), default=list, blank=True)

    class Meta:
        verbose_name_plural = "parties"
        ordering = ["name"]
        indexes = [GinIndex(fields=["legacy_ids"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Keep ``normalised_name`` (lower-cased, single-spaced) in step with ``name`` for matching."""
        self.normalised_name = " ".join(self.name.lower().split())
        super().save(*args, **kwargs)


class WellUse(models.TextChoices):
    """Principal use of a well (item 7)."""

    INDUSTRIAL = "industrial", "Industrial"
    PRIVATE = "private", "Private"
    PUBLIC_SUPPLY = "public_supply", "Public supply"
    AGRICULTURAL = "agricultural", "Agricultural"
    OBSERVATION = "observation", "Observation / monitoring"
    OTHER = "other", "Other"


class Well(PublishableModel):
    """A well or borehole (items 1, 2, 7, 8) with its current status.

    Status *over time* is kept in :class:`WellStatusEvent`; the boolean flags
    here are the current picture and are updated when an event is recorded.
    """

    # identification (item 2)
    name = models.CharField(max_length=150, db_index=True)
    aliases = ArrayField(models.CharField(max_length=150), default=list, blank=True)
    legacy_ids = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    photo = models.ImageField(upload_to="wells/photos/%Y/", blank=True)
    current_owner = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="owned_wells")
    driller = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="drilled_wells")
    compiled_by = models.CharField("Employee who compiled original record", max_length=150, blank=True)
    licence_number = models.CharField(max_length=64, blank=True, db_index=True)
    # location (item 1)
    location = gis.PointField(srid=SRID, null=True, blank=True)
    easting = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    northing = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    elevation_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    parish = models.ForeignKey(Parish, null=True, blank=True, on_delete=models.PROTECT, related_name="wells")
    basin = models.ForeignKey(Basin, null=True, blank=True, on_delete=models.PROTECT, related_name="wells")
    wmu = models.ForeignKey(WMU, null=True, blank=True, on_delete=models.PROTECT, related_name="wells")
    sub_wmu = models.ForeignKey(SubWMU, null=True, blank=True, on_delete=models.PROTECT, related_name="wells")
    hydrostrat_unit = models.ForeignKey(HydrostratUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="wells")
    # current status (item 7)
    pump_attached = models.BooleanField(null=True, blank=True)
    is_pumping = models.BooleanField(null=True, blank=True)
    is_licensed = models.BooleanField(null=True, blank=True)
    is_abandoned = models.BooleanField(default=False)
    is_replacement = models.BooleanField(default=False)
    is_index_well = models.BooleanField(default=False)
    use = models.CharField(max_length=16, choices=WellUse.choices, blank=True)
    replaces = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replaced_by")
    # history (item 8)
    completion_date = models.DateField(null=True, blank=True)
    pump_test_date = models.DateField(null=True, blank=True)
    abandoned_date = models.DateField(null=True, blank=True)
    replacement_date = models.DateField(null=True, blank=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        indexes = [GinIndex(fields=["aliases"]), GinIndex(fields=["legacy_ids"])]
        constraints = [models.UniqueConstraint(fields=["name"], name="uq_well_name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Derive the PostGIS point from easting/northing when only the grid values were supplied."""
        if self.location is None and self.easting is not None and self.northing is not None:
            from django.contrib.gis.geos import Point

            self.location = Point(float(self.easting), float(self.northing), srid=SRID)
        super().save(*args, **kwargs)


def _depth_order_constraint(name: str) -> models.CheckConstraint:
    """Check constraint: ``depth_to_m >= depth_from_m`` whenever both are set."""
    return models.CheckConstraint(
        condition=models.Q(depth_to_m__isnull=True) | models.Q(depth_from_m__isnull=True) | models.Q(depth_to_m__gte=models.F("depth_from_m")),
        name=name,
    )


class DepthIntervalMixin(models.Model):
    """``depth_from_m``/``depth_to_m`` with a check that the interval is ordered."""

    depth_from_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    depth_to_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        abstract = True

    @property
    def thickness_m(self):
        """Interval thickness when both depths are known."""
        if self.depth_from_m is None or self.depth_to_m is None:
            return None
        return self.depth_to_m - self.depth_from_m


class WellLithology(DepthIntervalMixin, AuditedModel):
    """Item 4 — one stratum of a well's lithological log, ordered by ``sequence``."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="lithology")
    sequence = models.PositiveSmallIntegerField(default=1)
    strata_type = models.CharField(max_length=100)
    strata_thickness_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "sequence"]
        verbose_name_plural = "well lithology"
        constraints = [
            models.UniqueConstraint(fields=["well", "sequence"], name="uq_lithology_well_sequence"),
            _depth_order_constraint("ck_lithology_depths"),
        ]

    def __str__(self):
        return f"{self.well} #{self.sequence} {self.strata_type}"


class WellCasing(DepthIntervalMixin, AuditedModel):
    """Item 5 — a casing or screen string in a well."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="casings")
    casing_type = models.CharField(max_length=100)
    diameter_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    thickness_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_screen = models.BooleanField(default=False, help_text="Tick for screened (perforated) intervals")
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "depth_from_m"]
        constraints = [
            _depth_order_constraint("ck_casing_depths"),
        ]

    def __str__(self):
        return f"{self.well} {self.casing_type} {self.depth_from_m}–{self.depth_to_m} m"


class WellPumpTest(AuditedModel):
    """Item 9 — step and constant-rate pumping test results for a well."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="pump_tests")
    tested_on = models.DateField(null=True, blank=True)
    duration_hours = models.DecimalField(max_digits=6, decimal_places=1, null=True, blank=True)
    static_water_level_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    specific_capacity_m3_d_m = models.DecimalField("Specific capacity (m³/d per m drawdown)", max_digits=12, decimal_places=3, null=True, blank=True)
    transmissivity_m2_d = models.DecimalField("Transmissivity (m²/d)", max_digits=12, decimal_places=3, null=True, blank=True)
    tested_by = models.ForeignKey(Party, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    step_test_rate_m3_d = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    step_test_water_level_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    step_test_drawdown_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    constant_test_rate_m3_d = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    constant_test_water_level_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    constant_test_drawdown_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    remarks = models.CharField(max_length=255, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "-tested_on"]

    def __str__(self):
        return f"{self.well} pump test {self.tested_on or 'undated'}"

    def save(self, *args, **kwargs):
        """Fill specific capacity from the constant-rate test when it was not supplied."""
        if self.specific_capacity_m3_d_m is None and self.constant_test_rate_m3_d and self.constant_test_drawdown_m:
            self.specific_capacity_m3_d_m = round(self.constant_test_rate_m3_d / self.constant_test_drawdown_m, 3)
        super().save(*args, **kwargs)


class WellOwnershipHistory(AuditedModel):
    """Previous owners (item 8). Current owner is Well.current_owner."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="ownership_history")
    owner = models.ForeignKey(Party, on_delete=models.PROTECT, related_name="+")
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "-from_date"]
        verbose_name_plural = "well ownership history"

    def __str__(self):
        return f"{self.well} owned by {self.owner} from {self.from_date or '?'}"


class WellEvent(models.TextChoices):
    """Events in a well's life (items 7 and 8 — status and history over time)."""

    DRILLED = "drilled", "Drilled"
    COMPLETED = "completed", "Completed"
    PUMP_INSTALLED = "pump_installed", "Pump installed"
    PUMP_REMOVED = "pump_removed", "Pump removed"
    PUMPING_STARTED = "pumping_started", "Pumping started"
    PUMPING_STOPPED = "pumping_stopped", "Pumping stopped"
    LICENSED = "licensed", "Licence issued"
    LICENCE_EXPIRED = "licence_expired", "Licence expired / revoked"
    REHABILITATED = "rehabilitated", "Rehabilitated"
    ABANDONED = "abandoned", "Abandoned"
    REPLACED = "replaced", "Replaced by another well"
    INSPECTED = "inspected", "Inspected"
    OTHER = "other", "Other"


#: Which Well flag each event sets (value None = leave unchanged).
_EVENT_EFFECTS: dict[str, dict[str, object]] = {
    WellEvent.COMPLETED: {},
    WellEvent.PUMP_INSTALLED: {"pump_attached": True},
    WellEvent.PUMP_REMOVED: {"pump_attached": False, "is_pumping": False},
    WellEvent.PUMPING_STARTED: {"is_pumping": True},
    WellEvent.PUMPING_STOPPED: {"is_pumping": False},
    WellEvent.LICENSED: {"is_licensed": True},
    WellEvent.LICENCE_EXPIRED: {"is_licensed": False},
    WellEvent.ABANDONED: {"is_abandoned": True, "is_pumping": False},
    WellEvent.REHABILITATED: {"is_abandoned": False},
}


class WellStatusEvent(AuditedModel):
    """Dated change in a well's status (items 7–8: 'status over time').

    Saving an event updates the matching current-status flag on the well, so the
    well record and its history never disagree. The date columns on ``Well``
    (``completion_date`` etc.) are filled from the first matching event.
    """

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="status_events")
    event = models.CharField(max_length=20, choices=WellEvent.choices)
    occurred_on = models.DateField(db_index=True)
    details = models.CharField(max_length=255, blank=True)
    related_well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", help_text="For 'replaced': the replacement well")
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "-occurred_on"]

    def __str__(self):
        return f"{self.well} {self.get_event_display()} {self.occurred_on:%Y-%m-%d}"

    def save(self, *args, **kwargs):
        """Save the event, then project its effect onto the well's current-status flags."""
        super().save(*args, **kwargs)
        updates = dict(_EVENT_EFFECTS.get(self.event, {}))
        date_field = {WellEvent.COMPLETED: "completion_date", WellEvent.ABANDONED: "abandoned_date", WellEvent.REPLACED: "replacement_date"}.get(self.event)
        if date_field and getattr(self.well, date_field) is None:
            updates[date_field] = self.occurred_on
        if self.event == WellEvent.REPLACED and self.related_well_id:
            updates["is_abandoned"] = True
            Well.objects.filter(pk=self.related_well_id).update(is_replacement=True, replaces=self.well)
        if updates:
            Well.objects.filter(pk=self.well_id).update(**updates)


class StreamflowStation(PublishableModel):
    """Streamflow gauging station (items 11–13)."""

    name = models.CharField(max_length=150, db_index=True)
    aliases = ArrayField(models.CharField(max_length=150), default=list, blank=True)
    legacy_ids = ArrayField(models.CharField(max_length=64), default=list, blank=True)
    aquarius_identifier = models.CharField(max_length=120, blank=True, db_index=True)
    photo = models.ImageField(upload_to="stations/photos/%Y/", blank=True)
    location_map = models.FileField(upload_to="stations/maps/%Y/", blank=True)
    river = models.ForeignKey(River, null=True, blank=True, on_delete=models.PROTECT, related_name="stations")
    location = gis.PointField(srid=SRID, null=True, blank=True)
    easting = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    northing = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    elevation_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    parish = models.ForeignKey(Parish, null=True, blank=True, on_delete=models.PROTECT, related_name="stations")
    basin = models.ForeignKey(Basin, null=True, blank=True, on_delete=models.PROTECT, related_name="stations")
    wmu = models.ForeignKey(WMU, null=True, blank=True, on_delete=models.PROTECT, related_name="stations")
    is_active = models.BooleanField(default=True)

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        indexes = [GinIndex(fields=["aliases"])]
        constraints = [models.UniqueConstraint(fields=["name"], name="uq_station_name")]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Derive the PostGIS point from easting/northing when only the grid values were supplied."""
        if self.location is None and self.easting is not None and self.northing is not None:
            from django.contrib.gis.geos import Point

            self.location = Point(float(self.easting), float(self.northing), srid=SRID)
        super().save(*args, **kwargs)


class Spring(PublishableModel):
    """Water-quality samples may come from a spring (item 10 'Source')."""

    name = models.CharField(max_length=150, unique=True)
    location = gis.PointField(srid=SRID, null=True, blank=True)
    parish = models.ForeignKey(Parish, null=True, blank=True, on_delete=models.PROTECT)

    objects = PublishedQuerySet.as_manager()

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Site master record (design doc 14 §3.4)
# ---------------------------------------------------------------------------


class SiteLinkMixin(models.Model):
    """A row that belongs to exactly one of: a well or a streamflow station."""

    well = models.ForeignKey(Well, null=True, blank=True, on_delete=models.CASCADE, related_name="%(class)ss")
    station = models.ForeignKey(StreamflowStation, null=True, blank=True, on_delete=models.CASCADE, related_name="%(class)ss")

    class Meta:
        abstract = True

    @property
    def site(self):
        """The well or station this row belongs to."""
        return self.well or self.station


def _one_site_constraint(name: str) -> models.CheckConstraint:
    """Check constraint: exactly one of well/station is set."""
    return models.CheckConstraint(
        condition=(models.Q(well__isnull=False, station__isnull=True) | models.Q(well__isnull=True, station__isnull=False)),
        name=name,
    )


class InstrumentKind(models.TextChoices):
    """Types of instrument WRA deploys at wells and stations."""

    LEVEL_LOGGER = "level_logger", "Water-level logger / pressure transducer"
    STAGE_RECORDER = "stage_recorder", "Stage recorder (float / bubbler / radar)"
    RAIN_GAUGE = "rain_gauge", "Rain gauge"
    FLOW_METER = "flow_meter", "Abstraction flow meter"
    EC_TEMP_PROBE = "ec_temp_probe", "Conductivity / temperature probe"
    CURRENT_METER = "current_meter", "Current meter / ADCP (gauging)"
    TELEMETRY = "telemetry", "Telemetry unit"
    OTHER = "other", "Other"


class Instrument(AuditedModel):
    """A physical instrument WRA owns or maintains, identified by serial number."""

    kind = models.CharField(max_length=16, choices=InstrumentKind.choices)
    make = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    serial_number = models.CharField(max_length=100, unique=True)
    asset_tag = models.CharField(max_length=64, blank=True)
    calibration_due_on = models.DateField(null=True, blank=True)
    is_retired = models.BooleanField(default=False)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["kind", "serial_number"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.make} {self.model} s/n {self.serial_number}".strip()

    @property
    def current_installation(self):
        """Where the instrument is installed now, or None if in store."""
        return self.installations.filter(removed_on__isnull=True).select_related("well", "station").first()


class InstrumentInstallation(SiteLinkMixin, AuditedModel):
    """A period during which an instrument was installed at a site."""

    instrument = models.ForeignKey(Instrument, on_delete=models.PROTECT, related_name="installations")
    installed_on = models.DateField()
    removed_on = models.DateField(null=True, blank=True)
    sensor_offset_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True, help_text="Sensor position relative to the reference point (m)")
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-installed_on"]
        constraints = [
            _one_site_constraint("ck_installation_one_site"),
            models.CheckConstraint(condition=models.Q(removed_on__isnull=True) | models.Q(removed_on__gte=models.F("installed_on")), name="ck_installation_dates"),
        ]

    def __str__(self):
        return f"{self.instrument} at {self.site} from {self.installed_on}"


class ReferencePoint(SiteLinkMixin, AuditedModel):
    """History of the measuring point (datum) readings are referenced to.

    A new row is added whenever the casing top is cut, the gauge board is
    re-set or the datum is re-surveyed; readings before/after can then be
    shifted correctly (RecordHistory method ``shift``).
    """

    description = models.CharField(max_length=150, help_text="e.g. Top of casing, north side")
    elevation_m = models.DecimalField("Elevation (m above datum)", max_digits=8, decimal_places=3, null=True, blank=True)
    height_above_ground_m = models.DecimalField(max_digits=6, decimal_places=3, null=True, blank=True)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    surveyed_by = models.CharField(max_length=150, blank=True)
    remarks = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-valid_from"]
        constraints = [
            _one_site_constraint("ck_refpoint_one_site"),
            models.CheckConstraint(condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=models.F("valid_from")), name="ck_refpoint_dates"),
        ]

    def __str__(self):
        return f"{self.site}: {self.description} from {self.valid_from}"


class VisitPurpose(models.TextChoices):
    """Why a site was visited."""

    ROUTINE = "routine", "Routine round"
    GAUGING = "gauging", "Discharge gauging"
    SAMPLING = "sampling", "Water-quality sampling"
    DOWNLOAD = "download", "Logger download"
    MAINTENANCE = "maintenance", "Maintenance / repair"
    CALIBRATION = "calibration", "Calibration"
    INSPECTION = "inspection", "Inspection / compliance"
    INSTALLATION = "installation", "Installation / removal"
    OTHER = "other", "Other"


class SiteVisit(SiteLinkMixin, AuditedModel):
    """Field visit log (design doc 14 §3.4): who went, why, what was found, what is due next."""

    visited_on = models.DateField(db_index=True)
    visited_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="site_visits")
    party_names = models.CharField(max_length=200, blank=True, help_text="Other people present")
    purpose = models.CharField(max_length=16, choices=VisitPurpose.choices, default=VisitPurpose.ROUTINE)
    findings = models.TextField(blank=True)
    actions_taken = models.TextField(blank=True)
    follow_up = models.CharField(max_length=255, blank=True)
    follow_up_due_on = models.DateField(null=True, blank=True)
    instrument = models.ForeignKey(Instrument, null=True, blank=True, on_delete=models.SET_NULL, related_name="visits")
    photo = models.ImageField(upload_to="visits/%Y/%m/", blank=True)

    class Meta:
        ordering = ["-visited_on"]
        constraints = [_one_site_constraint("ck_visit_one_site")]

    def __str__(self):
        return f"{self.site} {self.get_purpose_display()} {self.visited_on:%Y-%m-%d}"
