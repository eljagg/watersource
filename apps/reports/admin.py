"""Admin console entry for the dashboard / wall display settings."""
from django.contrib import admin

from .models import DisplaySettings


@admin.register(DisplaySettings)
class DisplaySettingsAdmin(admin.ModelAdmin):
    """Single row: rotation, refresh intervals, order and theme of the wall."""

    fieldsets = (
        ("Wall display", {"fields": ("rotate_seconds", "page_refresh_seconds", "wall_order", "wall_theme", "show_clock")}),
        ("Data freshness", {
            "fields": ("data_refresh_minutes",),
            "description": "The bi views are recalculated when older than this, by the scheduled job or on demand when a dashboard is opened.",
        }),
    )

    def has_add_permission(self, request):
        """One row only — it is created automatically."""
        return not DisplaySettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Never delete the settings row."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Jump straight to the single row."""
        from django.shortcuts import redirect
        from django.urls import reverse

        DisplaySettings.get()
        return redirect(reverse("admin:reports_displaysettings_change", args=[1]))
