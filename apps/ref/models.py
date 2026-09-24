"""
Reference and hydrological master data (ToR §C items 1, 2, 4, 5, 7, 8, 9, 11, 12).

Geometry is stored in EPSG:3448 (JAD2001 / Jamaica Metric Grid) as supplied by
WRA; exports transform to EPSG:4326. Parish/basin/WMU are assigned by spatial
join at load time when the lookup polygons are present, otherwise taken from the
source record.
"""
from django.contrib.gis.db import models as gis
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models

from apps.core.models import AuditedModel, PublishableModel, PublishedQuerySet

SRID = 3448


class CodedLookup(models.Model):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=150)
    geom = gis.MultiPolygonField(srid=SRID, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Parish(CodedLookup):
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
    wmu = models.ForeignKey(WMU, on_delete=models.PROTECT, related_name="sub_wmus")

    class Meta(CodedLookup.Meta):
        verbose_name = "sub-watershed management unit"


class HydrostratUnit(CodedLookup):
    KIND = [("aquifer", "Aquifer"), ("aquiclude", "Aquiclude"), ("aquitard", "Aquitard")]
    kind = models.CharField(max_length=16, choices=KIND, default="aquifer")

    class Meta(CodedLookup.Meta):
        verbose_name = "hydrostratigraphic unit"


class River(CodedLookup):
    pass


class PartyKind(models.TextChoices):
    OWNER = "owner", "Well owner"
    DRILLER = "driller", "Driller"
    APPLICANT = "applicant", "Licence applicant"
    LABORATORY = "laboratory", "Laboratory"
    ABSTRACTOR = "abstractor", "Licensed abstractor"
    OTHER = "other", "Other"


class Party(AuditedModel):
    """Owners, drillers, applicants, laboratories — de-duplicated in migration.
    Personal data lives here and in lic.*; never in a public view (ToR I.v)."""

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
        self.normalised_name = " ".join(self.name.lower().split())
        super().save(*args, **kwargs)


class WellUse(models.TextChoices):
    INDUSTRIAL = "industrial", "Industrial"
    PRIVATE = "private", "Private"
    PUBLIC_SUPPLY = "public_supply", "Public supply"
    AGRICULTURAL = "agricultural", "Agricultural"
    OBSERVATION = "observation", "Observation / monitoring"
    OTHER = "other", "Other"


class Well(PublishableModel):
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
        if self.location is None and self.easting is not None and self.northing is not None:
            from django.contrib.gis.geos import Point

            self.location = Point(float(self.easting), float(self.northing), srid=SRID)
        super().save(*args, **kwargs)


class WellLithology(AuditedModel):
    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="lithology")
    sequence = models.PositiveSmallIntegerField(default=1)
    strata_type = models.CharField(max_length=100)
    strata_thickness_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    depth_from_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    depth_to_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["well", "sequence"]
        verbose_name_plural = "well lithology"


class WellCasing(AuditedModel):
    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="casings")
    casing_type = models.CharField(max_length=100)
    diameter_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    thickness_mm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    depth_from_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    depth_to_m = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)


class WellPumpTest(AuditedModel):
    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="pump_tests")
    tested_on = models.DateField(null=True, blank=True)
    step_test_rate_m3_d = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    step_test_water_level_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    step_test_drawdown_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    constant_test_rate_m3_d = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    constant_test_water_level_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    constant_test_drawdown_m = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)


class WellOwnershipHistory(AuditedModel):
    """Previous owners (item 8). Current owner is Well.current_owner."""

    well = models.ForeignKey(Well, on_delete=models.CASCADE, related_name="ownership_history")
    owner = models.ForeignKey(Party, on_delete=models.PROTECT, related_name="+")
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    paper_ref = models.CharField(max_length=255, blank=True)
    electronic_ref = models.CharField(max_length=255, blank=True)


class StreamflowStation(PublishableModel):
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
