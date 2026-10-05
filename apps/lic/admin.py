"""Django admin for licence applications and licences (staff back-office)."""
from django.contrib import admin

from .models import ApplicationDocument, Licence, LicenceApplication, LicenceCondition, Sequence, TechnicalAssessment


class DocumentInline(admin.TabularInline):
    """Uploaded documents on the application page."""
    model = ApplicationDocument
    extra = 0
    readonly_fields = ("original_name", "content_type", "size", "sha256", "scan_status", "dspace_handle")


@admin.register(LicenceApplication)
class LicenceApplicationAdmin(admin.ModelAdmin):
    """Applications with status, parish and source filters."""
    list_display = ("reference", "applicant_name", "parish", "water_source", "status", "submitted_at", "decided_at")
    list_filter = ("status", "water_source", "parish", "kind")
    search_fields = ("reference", "applicant_name", "source_name")
    readonly_fields = ("reference", "submitted_at", "decided_at")
    inlines = [DocumentInline]


@admin.register(Licence)
class LicenceAdmin(admin.ModelAdmin):
    """Issued licences with expiry filters."""
    list_display = ("number", "licensee", "parish", "water_source", "daily_volume_granted_m3", "issued_on", "expires_on", "status")
    list_filter = ("status", "water_source", "parish")
    search_fields = ("number", "licensee__name", "source_name")
    readonly_fields = ("number", "expiry_alerts_sent", "expired_alert_sent_at")


admin.site.register(Sequence)


@admin.register(LicenceCondition)
class LicenceConditionAdmin(admin.ModelAdmin):
    """The conditions library hydrologists pick from at assessment."""

    list_display = ("code", "title", "category", "applies_to", "order", "is_default", "is_active")
    list_filter = ("category", "applies_to", "is_default", "is_active")
    search_fields = ("code", "title", "text")
    list_editable = ("order", "is_default", "is_active")


@admin.register(TechnicalAssessment)
class TechnicalAssessmentAdmin(admin.ModelAdmin):
    """Assessments on record (edit through the application's assessment page)."""

    list_display = ("application", "assessed_by", "assessed_at", "wmu", "aquifer", "impact", "recommendation", "recommended_daily_volume_m3")
    list_filter = ("recommendation", "impact", "wmu")
    search_fields = ("application__reference", "application__source_name")
    autocomplete_fields = ("application",)
    filter_horizontal = ("conditions",)
    readonly_fields = ("wmu_safe_yield_m3_d", "wmu_allocated_m3_d", "wmu_reported_m3_d", "created_by", "created_at", "updated_by", "updated_at")
