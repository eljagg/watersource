from django.contrib import admin

from .models import AuditLog, Notification


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("at", "actor", "action", "content_type", "object_id", "summary", "ip_address")
    list_filter = ("action", "content_type")
    search_fields = ("summary", "object_id", "actor__email")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "kind", "title", "read_at", "email_sent_at")
    list_filter = ("kind",)
    search_fields = ("title", "user__email")
