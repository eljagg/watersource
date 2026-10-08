"""Admin for the cleansing queue and adoption sign-offs (the console page is the working surface; this is for oversight)."""
from django.contrib import admin

from .models import AdoptionSignoff, CleansingIssue


@admin.register(CleansingIssue)
class CleansingIssueAdmin(admin.ModelAdmin):
    """Cleansing issues across all units."""

    list_display = ("id", "unit", "kind", "column", "summary", "rows_affected", "status", "decision", "decided_by", "decided_at")
    list_filter = ("unit", "status", "kind", "decision")
    search_fields = ("summary", "source", "column", "decision_note")
    readonly_fields = ("decided_by", "decided_at")


@admin.register(AdoptionSignoff)
class AdoptionSignoffAdmin(admin.ModelAdmin):
    """Adoption sign-offs per unit."""

    list_display = ("unit", "signed_by", "signed_at", "complete")
    list_filter = ("unit",)
