from django.contrib import admin

from .models import WorkflowAction, WorkflowDefinition, WorkflowInstance, WorkflowStage


class StageInline(admin.TabularInline):
    model = WorkflowStage
    extra = 0
    fields = ("order", "code", "name", "approver_group", "can_return_to_submitter", "can_reject", "sla_days")


@admin.register(WorkflowDefinition)
class WorkflowDefinitionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active")
    inlines = [StageInline]


@admin.register(WorkflowStage)
class WorkflowStageAdmin(admin.ModelAdmin):
    list_display = ("definition", "order", "name", "approver_group", "can_reject", "can_return_to_submitter")
    list_filter = ("definition",)
    filter_horizontal = ("can_return_to",)


class ActionInline(admin.TabularInline):
    model = WorkflowAction
    extra = 0
    can_delete = False
    readonly_fields = ("action", "actor", "from_stage", "to_stage", "comment", "at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(WorkflowInstance)
class WorkflowInstanceAdmin(admin.ModelAdmin):
    list_display = ("id", "definition", "summary", "current_stage", "state", "submitter", "started_at", "closed_at")
    list_filter = ("definition", "state", "current_stage")
    search_fields = ("summary",)
    inlines = [ActionInline]
    readonly_fields = ("content_type", "object_id", "started_at", "closed_at")
