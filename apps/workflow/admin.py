"""Django admin for workflow definitions and instances (ToR H.viii: administrators configure stages)."""
from django.contrib import admin

from .models import WorkflowAction, WorkflowDefinition, WorkflowInstance, WorkflowStage


class StageInline(admin.TabularInline):
    """Stages of a definition in order."""
    model = WorkflowStage
    extra = 0
    fields = ("order", "code", "name", "approver_group", "can_return_to_submitter", "can_reject", "sla_days")


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    """Workflow definitions."""
    list_display = ("code", "name", "is_active")
    inlines = [StageInline]


@admin.register(WorkflowStage)
class WorkflowStageAdmin(admin.ModelAdmin):
    """Stages with their approver group and return targets."""
    list_display = ("definition", "order", "name", "approver_group", "can_reject", "can_return_to_submitter")
    list_filter = ("definition",)
    filter_horizontal = ("can_return_to",)


class ActionInline(admin.TabularInline):
    """Action history of an instance (read-only)."""
    model = WorkflowAction
    extra = 0
    can_delete = False
    readonly_fields = ("action", "actor", "from_stage", "to_stage", "comment", "at")

    def has_add_permission(self, request, obj=None):
        """Actions are recorded by the engine only."""
        return False


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    """Live and closed workflow instances."""
    list_display = ("id", "definition", "summary", "current_stage", "state", "submitter", "started_at", "closed_at")
    list_filter = ("definition", "state", "current_stage")
    search_fields = ("summary",)
    inlines = [ActionInline]
    readonly_fields = ("content_type", "object_id", "started_at", "closed_at")
