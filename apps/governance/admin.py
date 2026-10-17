"""Admin: milestones (titles, dates and payment shares are edited here; decisions are made on the executive view)."""
from django.contrib import admin

from .models import Milestone


@admin.register(Milestone)
class MilestoneAdmin(admin.ModelAdmin):
    """Contract milestones."""

    list_display = ("code", "title", "due_week", "due_date", "payment_pct", "status", "delivered_on", "decided_at", "decided_by")
    list_filter = ("status",)
    search_fields = ("code", "title")
    readonly_fields = ("decided_at", "decided_by", "remarks")
    ordering = ("number",)
