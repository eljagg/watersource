"""Reference features copied from WRA's published GIS (v0.11.0).

Basins, WMUs, parishes and aquifers keep their own tables in ``apps.ref``;
everything else WRA publishes that the map draws — rivers, gauging stations,
sub-WMUs, the 2018 hydrostratigraphy — lands here as plain features with the
attributes WRA gave them, so a new WRA layer never needs a new table.
"""
from django.contrib.gis.db import models as gis
from django.db import models
from django.utils import timezone

from apps.ref.models import SRID


class WraLayer(models.TextChoices):
    """Layers ``load_wra_layers`` can fill."""

    RIVERS = "rivers", "Rivers and waterways"
    GAUGES = "gauges", "Stream gauging stations"
    SUBWMUS = "subwmus", "Sub-WMUs"
    HYDROSTRAT = "hydrostrat", "Hydrostratigraphy 2018"


class WraFeature(models.Model):
    """One feature of a WRA layer, as published on the Government of Jamaica ArcGIS Online."""

    layer = models.CharField(max_length=20, choices=WraLayer.choices, db_index=True)
    feature_id = models.CharField(max_length=64, help_text="WRA's own identifier (FID / station code).")
    name = models.CharField(max_length=200, blank=True)
    props = models.JSONField(default=dict, blank=True)
    geom = gis.GeometryField(srid=SRID)
    source = models.CharField(max_length=200, blank=True)
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["layer", "name"]
        constraints = [models.UniqueConstraint(fields=["layer", "feature_id"], name="wrafeature_layer_id")]
        verbose_name = "WRA feature"

    def __str__(self):
        return f"{self.get_layer_display()}: {self.name or self.feature_id}"
