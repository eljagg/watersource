"""Published documents for the public repository (curated by the Information & Documentation Unit)."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class DocumentCategory(models.TextChoices):
    """Shelves in the public repository."""

    REPORT = "report", "Report or bulletin"
    GUIDELINE = "guideline", "Guideline or standard"
    FORM = "form", "Form or application guide"
    NOTICE = "notice", "Public notice"
    DATASET_NOTE = "dataset_note", "Dataset documentation"
    OTHER = "other", "Other"


PUBLIC_DOCUMENT_TYPES = {"application/pdf": [".pdf"], "text/csv": [".csv"], "text/plain": [".csv", ".txt"],
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"]}


class PublishedDocument(TimeStampedModel):
    """A file WRA publishes for anyone to read: no personal data, no restricted detail."""

    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, help_text="One or two sentences shown in the listing.")
    category = models.CharField(max_length=16, choices=DocumentCategory.choices, default=DocumentCategory.REPORT, db_index=True)
    file = models.FileField(upload_to="public/%Y/%m/")
    original_name = models.CharField(max_length=255, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    published_on = models.DateField(default=timezone.localdate)
    is_published = models.BooleanField(default=True, help_text="Untick to take it off the public page without deleting it.")
    unit = models.ForeignKey("accounts.Unit", null=True, blank=True, on_delete=models.SET_NULL, related_name="published_documents",
                             help_text="Curating unit (normally Information & Documentation).")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="published_documents")
    downloads = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering = ["-published_on", "-created_at"]
        verbose_name = "published document"

    def __str__(self):
        return self.title

    def clean(self):
        """Only PDF, CSV, TXT or XLSX, checked by content, and within the upload size limit."""
        from apps.core.uploads import validate_upload

        f = self.file
        if f and hasattr(f, "file") and getattr(f, "_committed", True) is False:
            validate_upload(f, allowed=PUBLIC_DOCUMENT_TYPES)
            self.original_name = Path(f.name).name
            self.size_bytes = f.size
        if not self.title.strip():
            raise ValidationError({"title": "A title is required."})

    @property
    def extension(self) -> str:
        """Upper-case file type for the listing."""
        return Path(self.original_name or self.file.name).suffix.lstrip(".").upper()
