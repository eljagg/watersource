from django.contrib import admin

from .models import GenericRecord, ImportRun, Submission, SubmissionRecord


class RecordInline(admin.TabularInline):
    model = SubmissionRecord
    extra = 0
    readonly_fields = ("row_no", "payload", "errors", "flags", "status", "promoted_object_id")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("id", "category_version", "submitter", "channel", "status", "row_count", "accepted_count", "flagged_count", "rejected_count", "classification", "created_at")
    list_filter = ("status", "channel", "category_version__category", "is_correction")
    readonly_fields = ("row_count", "accepted_count", "flagged_count", "rejected_count")
    inlines = [RecordInline]


admin.site.register(GenericRecord)
admin.site.register(ImportRun)
