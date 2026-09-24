from django.contrib import admin

from .models import ApplicationDocument, Licence, LicenceApplication, Sequence


class DocumentInline(admin.TabularInline):
    model = ApplicationDocument
    extra = 0
    readonly_fields = ("original_name", "content_type", "size", "sha256", "scan_status", "dspace_handle")


@admin.register(LicenceApplication)
class LicenceApplicationAdmin(admin.ModelAdmin):
    list_display = ("reference", "applicant_name", "parish", "water_source", "status", "submitted_at", "decided_at")
    list_filter = ("status", "water_source", "parish", "kind")
    search_fields = ("reference", "applicant_name", "source_name")
    readonly_fields = ("reference", "submitted_at", "decided_at")
    inlines = [DocumentInline]


@admin.register(Licence)
class LicenceAdmin(admin.ModelAdmin):
    list_display = ("number", "licensee", "parish", "water_source", "daily_volume_granted_m3", "issued_on", "expires_on", "status")
    list_filter = ("status", "water_source", "parish")
    search_fields = ("number", "licensee__name", "source_name")
    readonly_fields = ("number", "expiry_alerts_sent", "expired_alert_sent_at")


admin.site.register(Sequence)
