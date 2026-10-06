"""Maps and GIS app (v0.7.0): Leaflet map, GeoJSON layers, GeoPackage export."""
from django.apps import AppConfig


class MapsConfig(AppConfig):
    """App config."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.maps"
    verbose_name = "Maps and GIS"
