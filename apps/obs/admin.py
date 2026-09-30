"""Django admin for observation tables, record history and approval periods.

Observation rows show grade, qualifiers and approval state in the list so a
hydrologist can filter to "working, poor grade" in one click. Record history is
read-only here (append-only table).
"""
from django.contrib import admin

from .models import AbstractionRecord, ApprovalPeriod, RecordHistory, StationReading, WaterQualitySample, WellWaterLevel

_QA_FIELDS = ("grade", "qualifiers", "approval_state", "classification", "source")
_QA_FILTER = ("approval_state", "grade", "classification", "source")
_QA_READONLY = ("graded_by", "graded_at", "created_by", "created_at", "updated_by", "updated_at")


@admin.register(WellWaterLevel)
class WWLAdmin(admin.ModelAdmin):
    """Well water levels (item 3)."""

    list_display = ("well", "measured_at", "water_level_m", "well_state", *_QA_FIELDS)
    list_filter = (*_QA_FILTER, "well_state")
    search_fields = ("well__name",)
    date_hierarchy = "measured_at"
    autocomplete_fields = ("well",)
    readonly_fields = _QA_READONLY


@admin.register(StationReading)
class ReadingAdmin(admin.ModelAdmin):
    """Station stage and discharge (item 13)."""

    list_display = ("station", "read_at", "recorder_reading_m", "observer_reading_m", "discharge_m3_s", *_QA_FIELDS)
    list_filter = _QA_FILTER
    search_fields = ("station__name",)
    date_hierarchy = "read_at"
    readonly_fields = _QA_READONLY


@admin.register(AbstractionRecord)
class AbstractionAdmin(admin.ModelAdmin):
    """Abstraction records (item 6) with the over-limit flag."""

    list_display = ("licence", "well", "period_start", "period_end", "abstraction_volume_m3", "daily_volume_granted_m3", "over_limit", *_QA_FIELDS)
    list_filter = ("over_limit", *_QA_FILTER, "source_type")
    search_fields = ("licence__number", "well__name")
    autocomplete_fields = ("well",)
    readonly_fields = _QA_READONLY


@admin.register(WaterQualitySample)
class WQAdmin(admin.ModelAdmin):
    """Water-quality samples (item 10)."""

    list_display = ("site", "source_type", "sampled_at", "ph", "specific_conductivity_us_cm", "nitrate_mg_l", *_QA_FIELDS)
    list_filter = ("source_type", *_QA_FILTER)
    date_hierarchy = "sampled_at"
    autocomplete_fields = ("well",)
    readonly_fields = _QA_READONLY


@admin.register(ApprovalPeriod)
class ApprovalPeriodAdmin(admin.ModelAdmin):
    """Approval periods opened by hydrologists (read-only; use the service to create)."""

    list_display = ("series", "site", "starts_at", "ends_at", "rows_approved", "approved_by", "approved_at", "reopened_at")
    list_filter = ("series",)
    readonly_fields = [f.name for f in ApprovalPeriod._meta.fields]

    def has_add_permission(self, request):
        """Periods are created through ``obs.services.approve_period`` only."""
        return False


@admin.register(RecordHistory)
class HistoryAdmin(admin.ModelAdmin):
    """Append-only correction history."""

    list_display = ("content_type", "object_id", "method", "corrected_by", "corrected_at", "approved_by", "approved_at")
    list_filter = ("method",)
    readonly_fields = [f.name for f in RecordHistory._meta.fields]

    def has_add_permission(self, request):
        """Rows are written by services only."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Append-only table."""
        return False
