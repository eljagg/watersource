"""Admin: the Information & Documentation Unit publishes and withdraws documents here."""
from django.contrib import admin

from .models import PublishedDocument


@admin.register(PublishedDocument)
class PublishedDocumentAdmin(admin.ModelAdmin):
    """Published documents (the public page is the reading surface)."""

    list_display = ("title", "category", "published_on", "unit", "is_published", "extension", "downloads")
    list_filter = ("category", "is_published", "unit")
    search_fields = ("title", "summary", "original_name")
    readonly_fields = ("original_name", "size_bytes", "downloads", "published_by")
    fields = ("title", "category", "summary", "file", "published_on", "is_published", "unit", "original_name", "size_bytes", "downloads", "published_by")

    def save_model(self, request, obj, form, change):
        """Record who published it."""
        if not obj.published_by_id:
            obj.published_by = request.user
        if not obj.unit_id and getattr(request.user, "unit_id", None):
            obj.unit = request.user.unit
        super().save_model(request, obj, form, change)
