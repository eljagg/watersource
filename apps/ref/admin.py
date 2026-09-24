from django.contrib.gis import admin

from .models import (
    WMU,
    Basin,
    HydrostratUnit,
    Parish,
    Party,
    River,
    Spring,
    StreamflowStation,
    SubWMU,
    Well,
    WellCasing,
    WellLithology,
    WellOwnershipHistory,
    WellPumpTest,
)


class LithologyInline(admin.TabularInline):
    model = WellLithology
    extra = 0


class CasingInline(admin.TabularInline):
    model = WellCasing
    extra = 0


class PumpTestInline(admin.TabularInline):
    model = WellPumpTest
    extra = 0


class OwnershipInline(admin.TabularInline):
    model = WellOwnershipHistory
    extra = 0


@admin.register(Well)
class WellAdmin(admin.GISModelAdmin):
    list_display = ("name", "parish", "basin", "wmu", "use", "is_licensed", "is_abandoned", "approval_state", "classification")
    list_filter = ("parish", "basin", "use", "is_licensed", "is_abandoned", "approval_state", "classification")
    search_fields = ("name", "aliases", "licence_number", "legacy_ids")
    inlines = [LithologyInline, CasingInline, PumpTestInline, OwnershipInline]
    autocomplete_fields = ("current_owner", "driller")


@admin.register(StreamflowStation)
class StationAdmin(admin.GISModelAdmin):
    list_display = ("name", "river", "parish", "is_active", "approval_state", "classification")
    search_fields = ("name", "aliases", "aquarius_identifier")
    list_filter = ("parish", "is_active", "classification")


@admin.register(Party)
class PartyAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "email", "phone", "is_organisation", "merged_into")
    search_fields = ("name", "email", "legacy_ids")
    list_filter = ("kind",)


for m in (Parish, Basin, WMU, SubWMU, HydrostratUnit, River, Spring):
    admin.site.register(m, admin.GISModelAdmin)
