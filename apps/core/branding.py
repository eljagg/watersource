"""Site branding — organisation name, product name, tagline and logo, edited by WRA in the admin console.

One row (``SiteBranding.get()``); the logo bytes live in the database so the
same image is served from every web container without a shared disk (Railway
staging and the WRA app-vm alike). Templates read it through the ``branding``
context variable; the admin console header uses it too.
"""
from __future__ import annotations

from django.core.cache import cache
from django.db import models

CACHE_KEY = "branding:row"
LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "image/svg+xml": "svg"}
LOGO_MAX_BYTES = 512 * 1024


class SiteBranding(models.Model):
    """Names and logo shown in the header, footer, wall display and admin console."""

    organisation_name = models.CharField("Organisation name", max_length=120, default="Water Resources Authority of Jamaica",
                                         help_text="Shown in the footer and on the wall display.")
    product_name = models.CharField("Application name", max_length=40, default="WaterSource", help_text="Shown next to the logo and in the browser tab.")
    tagline = models.CharField("Tagline", max_length=80, default="Jamaica · WRA", blank=True, help_text="Small line under the application name in the header.")
    footer_text = models.CharField("Footer line", max_length=200, blank=True, default="",
                                   help_text="Optional. Leave empty to show the organisation name.")
    logo = models.BinaryField("Logo", blank=True, null=True, editable=False)
    logo_type = models.CharField(max_length=20, blank=True, default="", editable=False)
    logo_dark = models.BinaryField("Logo for dark backgrounds", blank=True, null=True, editable=False)
    logo_dark_type = models.CharField(max_length=20, blank=True, default="", editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site branding"
        verbose_name_plural = "site branding"

    def __str__(self):
        return f"{self.product_name} branding"

    def save(self, *args, **kwargs):
        """Enforce the singleton and drop the cached copy."""
        self.pk = 1
        super().save(*args, **kwargs)
        cache.delete(CACHE_KEY)

    @classmethod
    def get(cls) -> SiteBranding:
        """The single row, cached for a minute, created with defaults on first use."""
        row = cache.get(CACHE_KEY)
        if row is None:
            row, _ = cls.objects.get_or_create(pk=1)
            cache.set(CACHE_KEY, row, 60)
        return row

    @property
    def has_logo(self) -> bool:
        """Whether a logo has been uploaded."""
        return bool(self.logo)

    @property
    def has_logo_dark(self) -> bool:
        """Whether a separate dark-background logo has been uploaded."""
        return bool(self.logo_dark)

    @property
    def version(self) -> int:
        """Cache-buster for the logo URL."""
        return int(self.updated_at.timestamp()) if self.updated_at else 0

    @property
    def page_title(self) -> str:
        """Browser-tab title."""
        return f"{self.product_name} {self.tagline}".strip() if self.tagline else self.product_name

    @property
    def footer(self) -> str:
        """Footer line with the organisation name as the fallback."""
        return self.footer_text or self.organisation_name
