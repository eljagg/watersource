"""Django admin for users, API keys and email tokens (ToR H.i: administrators manage accounts here)."""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import APIKey, EmailToken, Unit, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """User administration: roles (groups), type, verification and lock state."""
    ordering = ["email"]
    list_display = ("email", "full_name", "user_type", "unit", "is_super_user", "is_active", "email_verified_at", "last_login")
    list_filter = ("user_type", "unit", "is_super_user", "is_active", "groups")
    search_fields = ("email", "full_name", "organisation")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "organisation", "user_type", "party")}),
        ("WRA unit", {"fields": ("unit", "is_super_user"),
                      "description": "Branch membership from the stakeholder model; the Super User flag is informational "
                                     "(training, adoption sign-off, first-line support) and grants no permission."}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified_at", "must_change_password", "password_changed_at", "anonymised_at")}),
        ("Roles", {"fields": ("groups",)}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "user_type", "password1", "password2")}),)
    readonly_fields = ("password_changed_at", "anonymised_at")


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    """API keys: only the prefix is visible; keys are revoked here, never edited."""
    list_display = ("name", "prefix", "user", "created_at", "expires_at", "last_used_at", "revoked_at")
    readonly_fields = ("prefix", "key_hash", "last_used_at")


@admin.register(EmailToken)
class EmailTokenAdmin(admin.ModelAdmin):
    """Email verification tokens (read-only troubleshooting view)."""
    list_display = ("user", "purpose", "created_at", "expires_at", "used_at")


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    """WRA branches with their system role and Super Users."""

    list_display = ("name", "code", "division", "is_operating", "has_super_user", "super_user_names", "is_active")
    list_filter = ("division", "is_operating", "has_super_user")
    search_fields = ("name", "code", "responsibilities")
    readonly_fields = ("owns",)

    @admin.display(description="Owns (approves in workflow)")
    def owns(self, obj):
        """Everything this unit owns: reference families (code), submission categories and workflow stages (editable on those pages)."""
        from apps.accounts.ownership import families_owned_by

        parts = []
        fam = families_owned_by(obj.code)
        if fam:
            parts.append("Data: " + ", ".join(fam))
        cats = list(obj.categories.values_list("name", flat=True))
        if cats:
            parts.append("Submission categories: " + ", ".join(cats))
        stages = [f"{s.definition.name} › {s.name}" for s in obj.workflow_stages.select_related("definition")]
        if stages:
            parts.append("Workflow stages: " + "; ".join(stages))
        return " · ".join(parts) or "—"

    @admin.display(description="Super User(s)")
    def super_user_names(self, obj):
        """Who holds the Super User role for the unit."""
        return ", ".join(u.full_name for u in obj.super_users) or "—"
