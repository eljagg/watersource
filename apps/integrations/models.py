"""Evidence trail for every integration and export run (design plan §5)."""
from django.db import models


class IntegrationSystem(models.TextChoices):
    AQUARIUS = "aquarius", "Aquarius Time-Series"
    HGA = "hga", "Hydro GeoAnalyst"
    DSPACE = "dspace", "DSpace"
    ARCGIS = "arcgis", "ArcGIS Enterprise export"
    FINANCE = "finance", "Finance & Accounts export"


class IntegrationRun(models.Model):
    system = models.CharField(max_length=16, choices=IntegrationSystem.choices, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default="running")
    records_read = models.PositiveIntegerField(default=0)
    records_written = models.PositiveIntegerField(default=0)
    detail = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    output_path = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.system} {self.started_at:%Y-%m-%d %H:%M} {self.status}"

    def finish(self, status="ok", **detail):
        from django.utils import timezone

        self.status = status
        self.finished_at = timezone.now()
        self.detail.update(detail)
        self.save()
