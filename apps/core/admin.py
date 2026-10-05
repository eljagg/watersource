"""Django admin for the audit log (read-only), notifications and site branding."""
import io

import magic
from django import forms
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from PIL import Image

from . import audit
from .branding import LOGO_MAX_BYTES, LOGO_TYPES, SiteBranding
from .models import AuditLog, Notification


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only audit log browser."""
    list_display = ("at", "actor", "action", "content_type", "object_id", "summary", "ip_address")
    list_filter = ("action", "content_type")
    search_fields = ("summary", "object_id", "actor__email")
    readonly_fields = [f.name for f in AuditLog._meta.fields]

    def has_add_permission(self, request):
        """Never."""
        return False

    def has_change_permission(self, request, obj=None):
        """Never (view only)."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Never."""
        return False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """In-app notifications with email delivery status."""
    list_display = ("created_at", "user", "kind", "title", "read_at", "email_sent_at")
    list_filter = ("kind",)
    search_fields = ("title", "user__email")


# --- Site branding -------------------------------------------------------------------


class BrandingForm(forms.ModelForm):
    """Branding row plus two upload fields that store the image bytes in the database."""

    logo_upload = forms.FileField(label="Logo", required=False, help_text="PNG, JPEG, WebP or SVG, up to 512 KB. Shown about 36 px tall in the header — a wide logo works best.")
    logo_dark_upload = forms.FileField(label="Logo for dark backgrounds", required=False,
                                       help_text="Optional. Used when the site or the wall is in dark mode; otherwise the main logo is used.")
    remove_logo = forms.BooleanField(label="Remove the logo", required=False)
    remove_logo_dark = forms.BooleanField(label="Remove the dark-background logo", required=False)

    class Meta:
        model = SiteBranding
        fields = ("organisation_name", "product_name", "tagline", "footer_text", "copyright_text", "tile_color", "accent_color")
        widgets = {"tile_color": forms.TextInput(attrs={"type": "color"}), "accent_color": forms.TextInput(attrs={"type": "color"})}

    @staticmethod
    def _check(upload):
        """Validate type and size; returns (bytes, content_type)."""
        data = upload.read()
        if len(data) > LOGO_MAX_BYTES:
            raise forms.ValidationError("The image is larger than 512 KB.")
        ctype = magic.from_buffer(data, mime=True)
        if ctype in ("text/xml", "text/plain", "text/html") and b"<svg" in data[:2048]:
            ctype = "image/svg+xml"
        if ctype not in LOGO_TYPES:
            raise forms.ValidationError("Use a PNG, JPEG, WebP or SVG image.")
        if ctype == "image/svg+xml":
            low = data.lower()
            if b"<script" in low or b"onload=" in low or b"javascript:" in low:
                raise forms.ValidationError("The SVG contains scripting, which is not allowed.")
        else:
            try:
                Image.open(io.BytesIO(data)).verify()
            except Exception as exc:  # noqa: BLE001
                raise forms.ValidationError("The image could not be read.") from exc
        return data, ctype

    def clean_logo_upload(self):
        """Validate the main logo."""
        f = self.cleaned_data.get("logo_upload")
        return self._check(f) if f else None

    def clean_logo_dark_upload(self):
        """Validate the dark-background logo."""
        f = self.cleaned_data.get("logo_dark_upload")
        return self._check(f) if f else None

    def save(self, commit=True):
        """Store uploaded bytes on the row."""
        obj = super().save(commit=False)
        if self.cleaned_data.get("remove_logo"):
            obj.logo, obj.logo_type = None, ""
        if self.cleaned_data.get("remove_logo_dark"):
            obj.logo_dark, obj.logo_dark_type = None, ""
        if self.cleaned_data.get("logo_upload"):
            obj.logo, obj.logo_type = self.cleaned_data["logo_upload"]
        if self.cleaned_data.get("logo_dark_upload"):
            obj.logo_dark, obj.logo_dark_type = self.cleaned_data["logo_dark_upload"]
        if commit:
            obj.save()
        return obj


@admin.register(SiteBranding)
class SiteBrandingAdmin(admin.ModelAdmin):
    """Single row: names, tagline and logo used across the site."""

    form = BrandingForm
    fieldsets = (
        ("Names", {"fields": ("organisation_name", "product_name", "tagline", "footer_text", "copyright_text")}),
        ("Colours", {"fields": ("tile_color", "accent_color"),
                     "description": "Home-page tiles and navigation tabs use the tile colour with a thin metallic border in the border colour."}),
        ("Logo", {"fields": ("current_logo", "logo_upload", "remove_logo", "logo_dark_upload", "remove_logo_dark"),
                  "description": "Changes appear on every page within a minute. The logo replaces the blue droplet in the header and on the wall display."}),
    )
    readonly_fields = ("current_logo",)

    @admin.display(description="Current logo")
    def current_logo(self, obj):
        """Preview of the stored logos."""
        if obj is None or not obj.has_logo:
            return "No logo uploaded — the default droplet mark is shown."
        light = format_html('<img src="{}?v={}" alt="" style="height:40px;background:#fff;padding:4px;border-radius:6px">', reverse("core:branding_logo"), obj.version)
        if obj.has_logo_dark:
            dark = format_html(' <img src="{}?v={}" alt="" style="height:40px;background:#0f172a;padding:4px;border-radius:6px">', reverse("core:branding_logo_dark"), obj.version)
            return format_html("{}{}", light, dark)
        return light

    def has_add_permission(self, request):
        """One row only."""
        return not SiteBranding.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Never delete the row."""
        return False

    def changelist_view(self, request, extra_context=None):
        """Jump straight to the single row."""
        obj = SiteBranding.get()
        return redirect(reverse("admin:core_sitebranding_change", args=[obj.pk]))

    def save_model(self, request, obj, form, change):
        """Record who changed the branding."""
        super().save_model(request, obj, form, change)
        audit.log("branding.changed", obj, actor=request.user, summary=f"{obj.product_name} / {obj.organisation_name}")
