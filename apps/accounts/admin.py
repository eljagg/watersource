from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import APIKey, EmailToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ("email", "full_name", "user_type", "is_active", "email_verified_at", "last_login")
    list_filter = ("user_type", "is_active", "groups")
    search_fields = ("email", "full_name", "organisation")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name", "phone", "organisation", "user_type", "party")}),
        ("Status", {"fields": ("is_active", "is_staff", "is_superuser", "email_verified_at", "must_change_password", "password_changed_at", "anonymised_at")}),
        ("Roles", {"fields": ("groups",)}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "user_type", "password1", "password2")}),)
    readonly_fields = ("password_changed_at", "anonymised_at")


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "user", "created_at", "expires_at", "last_used_at", "revoked_at")
    readonly_fields = ("prefix", "key_hash", "last_used_at")


@admin.register(EmailToken)
class EmailTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "created_at", "expires_at", "used_at")
