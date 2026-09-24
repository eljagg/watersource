from django.contrib import admin, messages

from .models import CategoryField, CategoryRule, CategoryVersion, DataCategory


class FieldInline(admin.TabularInline):
    model = CategoryField
    extra = 0
    fields = ("order", "name", "label", "field_type", "unit", "required", "min_value", "max_value", "soft_min", "soft_max", "choices", "target_field")


class RuleInline(admin.TabularInline):
    model = CategoryRule
    extra = 0


@admin.register(CategoryVersion)
class CategoryVersionAdmin(admin.ModelAdmin):
    list_display = ("category", "version", "status", "published_at", "published_by")
    list_filter = ("status", "category")
    inlines = [FieldInline, RuleInline]
    readonly_fields = ("json_schema", "published_at", "published_by")
    actions = ["publish", "clone"]

    @admin.action(description="Publish selected draft versions")
    def publish(self, request, queryset):
        for v in queryset:
            try:
                v.publish(request.user)
                self.message_user(request, f"Published {v}.")
            except ValueError as exc:
                self.message_user(request, f"{v}: {exc}", level=messages.ERROR)

    @admin.action(description="Clone as new draft")
    def clone(self, request, queryset):
        for v in queryset:
            self.message_user(request, f"Created {v.clone_as_draft()}.")


class VersionInline(admin.TabularInline):
    model = CategoryVersion
    extra = 0
    fields = ("version", "status", "published_at")
    readonly_fields = ("published_at",)
    show_change_link = True


@admin.register(DataCategory)
class DataCategoryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "target_model", "link_kind", "workflow", "default_classification", "is_active")
    list_filter = ("is_active", "target_model")
    filter_horizontal = ("submitter_groups",)
    inlines = [VersionInline]
