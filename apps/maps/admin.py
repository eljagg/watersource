"""Admin: WRA reference features (read-only view of what load_wra_layers fetched)."""
from django.contrib import admin

from .models import WraFeature


@admin.register(WraFeature)
class WraFeatureAdmin(admin.ModelAdmin):
    """Browse the features copied from WRA's ArcGIS Online."""

    list_display = ("layer", "feature_id", "name", "fetched_at")
    list_filter = ("layer",)
    search_fields = ("name", "feature_id")
    readonly_fields = ("layer", "feature_id", "name", "props", "source", "fetched_at")
    exclude = ("geom",)
