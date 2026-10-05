"""Django admin for reference data and the site master record.

Staff with the ``administrator`` or ``updater`` role maintain lookups, wells
and stations here until the dedicated hydrologist screens arrive (Sprint 3).
Inlines put a well's lithology, casing, pump tests, ownership, status events,
instruments, reference points and visits on one page (design doc 14 §3.4).
"""
from django.contrib.gis import admin

from .models import (
    WMU,
    Aquifer,
    Basin,
    HydrostratUnit,
    Instrument,
    InstrumentInstallation,
    Parish,
    Party,
    Qualifier,
    ReferencePoint,
    River,
    SiteVisit,
    Spring,
    StreamflowStation,
    SubWMU,
    Well,
    WellCasing,
    WellLithology,
    WellOwnershipHistory,
    WellPumpTest,
    WellStatusEvent,
)


class LithologyInline(admin.TabularInline):
    """Lithology strata on the well page."""

    model = WellLithology
    extra = 0
    fields = ("sequence", "strata_type", "depth_from_m", "depth_to_m", "strata_thickness_m", "paper_ref")


class CasingInline(admin.TabularInline):
    """Casing / screen strings on the well page."""

    model = WellCasing
    extra = 0
    fields = ("casing_type", "is_screen", "diameter_mm", "thickness_mm", "depth_from_m", "depth_to_m")


class PumpTestInline(admin.TabularInline):
    """Pump tests on the well page."""

    model = WellPumpTest
    extra = 0
    fields = ("tested_on", "duration_hours", "static_water_level_m", "constant_test_rate_m3_d", "constant_test_drawdown_m", "specific_capacity_m3_d_m", "transmissivity_m2_d")


class OwnershipInline(admin.TabularInline):
    """Previous owners on the well page."""

    model = WellOwnershipHistory
    extra = 0
    autocomplete_fields = ("owner",)


class StatusEventInline(admin.TabularInline):
    """Dated status events on the well page (items 7–8)."""

    model = WellStatusEvent
    fk_name = "well"
    extra = 0
    fields = ("occurred_on", "event", "details", "related_well")
    autocomplete_fields = ("related_well",)


class InstallationInline(admin.TabularInline):
    """Instruments installed at the site."""

    model = InstrumentInstallation
    extra = 0
    fields = ("instrument", "installed_on", "removed_on", "sensor_offset_m", "remarks")
    autocomplete_fields = ("instrument",)


class ReferencePointInline(admin.TabularInline):
    """Reference-point (datum) history at the site."""

    model = ReferencePoint
    extra = 0
    fields = ("description", "elevation_m", "height_above_ground_m", "valid_from", "valid_to", "surveyed_by")


class VisitInline(admin.TabularInline):
    """Most recent visits at the site (full log under Site visits)."""

    model = SiteVisit
    extra = 0
    max_num = 10
    fields = ("visited_on", "purpose", "visited_by", "findings", "follow_up_due_on")
    readonly_fields = ("visited_by",)
    show_change_link = True


@admin.register(Well)
class WellAdmin(admin.GISModelAdmin):
    """Well master record with all item 2–9 detail as inlines."""

    list_display = ("name", "parish", "basin", "wmu", "use", "is_public_supply", "is_licensed", "is_pumping", "is_abandoned", "approval_state", "classification")
    list_filter = ("is_public_supply", "parish", "basin", "use", "is_licensed", "is_abandoned", "is_index_well", "approval_state", "classification")
    search_fields = ("name", "aliases", "licence_number", "legacy_ids")
    inlines = [StatusEventInline, LithologyInline, CasingInline, PumpTestInline, OwnershipInline, ReferencePointInline, InstallationInline, VisitInline]
    autocomplete_fields = ("current_owner", "driller", "replaces", "aquifer")
    readonly_fields = ("created_by", "created_at", "updated_by", "updated_at")


@admin.register(StreamflowStation)
class StationAdmin(admin.GISModelAdmin):
    """Streamflow station master record with site-master inlines."""

    list_display = ("name", "river", "parish", "is_active", "is_public_supply", "approval_state", "classification")
    search_fields = ("name", "aliases", "aquarius_identifier")
    list_filter = ("is_public_supply", "parish", "is_active", "classification")
    inlines = [ReferencePointInline, InstallationInline, VisitInline]


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    """Owners, drillers, applicants and laboratories."""

    list_display = ("name", "kind", "email", "phone", "is_organisation", "merged_into")
    search_fields = ("name", "email", "legacy_ids")
    list_filter = ("kind",)


@admin.register(Qualifier)
class QualifierAdmin(admin.ModelAdmin):
    """Observation qualifier codes."""

    list_display = ("code", "name", "applies_to", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    """Instrument register with current location."""

    list_display = ("serial_number", "kind", "make", "model", "calibration_due_on", "is_retired", "where")
    list_filter = ("kind", "is_retired")
    search_fields = ("serial_number", "asset_tag", "make", "model")
    inlines = [InstallationInline]

    @admin.display(description="Installed at")
    def where(self, obj):
        """Current site, for the list view."""
        inst = obj.current_installation
        return inst.site if inst else "—"


@admin.register(SiteVisit)
class SiteVisitAdmin(admin.ModelAdmin):
    """Full field-visit log across all sites."""

    list_display = ("visited_on", "site", "purpose", "visited_by", "follow_up_due_on")
    list_filter = ("purpose", "visited_on")
    search_fields = ("well__name", "station__name", "findings")
    autocomplete_fields = ("well", "station", "instrument")
    date_hierarchy = "visited_on"

    def save_model(self, request, obj, form, change):
        """Default ``visited_by`` to the person entering the visit."""
        if obj.visited_by_id is None:
            obj.visited_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WellStatusEvent)
class WellStatusEventAdmin(admin.ModelAdmin):
    """Well status events across all wells."""

    list_display = ("occurred_on", "well", "event", "details")
    list_filter = ("event",)
    search_fields = ("well__name",)
    autocomplete_fields = ("well", "related_well")
    date_hierarchy = "occurred_on"


@admin.register(WMU)
class WMUAdmin(admin.GISModelAdmin):
    """Watershed management units with their safe yield (used by the balance sheet)."""

    list_display = ("code", "name", "basin", "safe_yield_m3_d", "safe_yield_source")
    list_filter = ("basin",)
    search_fields = ("code", "name")


@admin.register(Aquifer)
class AquiferAdmin(admin.GISModelAdmin):
    """Aquifers (Planning & Investigation Unit)."""

    list_display = ("code", "name", "aquifer_type", "wmu", "basin", "safe_yield_m3_d", "is_saline_risk")
    list_filter = ("aquifer_type", "basin", "is_saline_risk")
    search_fields = ("code", "name")


for m in (Parish, Basin, SubWMU, HydrostratUnit, River, Spring):
    admin.site.register(m, admin.GISModelAdmin)
