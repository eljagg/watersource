"""Django admin for integration run history."""
from django.contrib import admin

from .models import IntegrationRun


@admin.register(IntegrationRun)
class IntegrationRunAdmin(admin.ModelAdmin):
    """Read-only list of sync/export runs with status and counts."""
    list_display = ("system", "started_at", "finished_at", "status", "records_read", "records_written", "output_path")
    list_filter = ("system", "status")
    readonly_fields = [f.name for f in IntegrationRun._meta.fields]
