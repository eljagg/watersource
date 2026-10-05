"""Display settings for the dashboards and wall (one row, edited in the admin console).

Reporting objects themselves are materialised views in the ``bi`` schema
(migrations 0001–0003, ``services.py``); this is the only ORM model in the app.
"""
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

DEFAULT_ORDER = ["licensing", "monitoring", "submissions", "executive"]


class DisplaySettings(models.Model):
    """How the wall display and dashboards behave — changed by WRA in the admin, no redeploy (design doc 13 §6)."""

    THEMES = [("dark", "Dark (recommended for the wall)"), ("light", "Light")]

    rotate_seconds = models.PositiveIntegerField("Seconds per dashboard on the wall", default=60, validators=[MinValueValidator(10), MaxValueValidator(3600)])
    page_refresh_seconds = models.PositiveIntegerField("Seconds between the wall re-fetching data", default=60, validators=[MinValueValidator(15), MaxValueValidator(3600)])
    data_refresh_minutes = models.PositiveIntegerField("Minutes between recalculations of the bi views", default=5, validators=[MinValueValidator(1), MaxValueValidator(1440)],
                                                       help_text="Dashboards show data no older than this. Lower = fresher, more database work.")
    wall_order = models.JSONField(
        "Dashboards shown on the wall, in order", default=list, blank=True,
        help_text='e.g. ["licensing", "monitoring", "submissions", "executive"]; empty = all four',
    )
    wall_theme = models.CharField(max_length=5, choices=THEMES, default="dark")
    show_clock = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "display settings"
        verbose_name_plural = "display settings"

    def __str__(self):
        return "Dashboard and wall display settings"

    def save(self, *args, **kwargs):
        """Enforce the singleton."""
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "DisplaySettings":
        """The single settings row, created with defaults on first use."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def order(self) -> list[str]:
        """Wall order with unknown slugs dropped; defaults when empty."""
        from .dashboards import DASHBOARDS

        wanted = [s for s in (self.wall_order or []) if s in DASHBOARDS]
        return wanted or DEFAULT_ORDER
