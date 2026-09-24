from django.contrib import admin

from .models import AbstractionRecord, RecordHistory, StationReading, WaterQualitySample, WellWaterLevel


@admin.register(WellWaterLevel)
class WWLAdmin(admin.ModelAdmin):
    list_display = ("well", "measured_at", "water_level_m", "well_state", "source", "approval_state", "classification")
    list_filter = ("approval_state", "classification", "source", "well_state")
    search_fields = ("well__name",)
    date_hierarchy = "measured_at"


@admin.register(StationReading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ("station", "read_at", "recorder_reading_m", "observer_reading_m", "source", "approval_state", "classification")
    list_filter = ("approval_state", "classification", "source")
    date_hierarchy = "read_at"


@admin.register(AbstractionRecord)
class AbstractionAdmin(admin.ModelAdmin):
    list_display = ("licence", "well", "period_start", "period_end", "abstraction_volume_m3", "daily_volume_granted_m3", "over_limit", "approval_state", "classification")
    list_filter = ("over_limit", "approval_state", "classification", "source_type")
    search_fields = ("licence__number", "well__name")


@admin.register(WaterQualitySample)
class WQAdmin(admin.ModelAdmin):
    list_display = ("site", "source_type", "sampled_at", "ph", "specific_conductivity_us_cm", "nitrate_mg_l", "approval_state", "classification")
    list_filter = ("source_type", "approval_state", "classification")
    date_hierarchy = "sampled_at"


@admin.register(RecordHistory)
class HistoryAdmin(admin.ModelAdmin):
    list_display = ("content_type", "object_id", "corrected_by", "corrected_at", "approved_by", "approved_at")
    readonly_fields = [f.name for f in RecordHistory._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
