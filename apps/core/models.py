"""
Core building blocks shared by every app.

- Classification / ApprovalState: the two enums the ToR hinges on (H.ix–x).
- TimeStampedModel / AuditedModel: who/when on every table.
- AuditLog: append-only record of every workflow action, correction,
  privileged download and admin change (ToR H.xvi, F.5).
- Notification: in-app notification row; the email copy is sent by a task
  so a user is informed whether or not they are logged in (ToR H.xi).
"""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from .middleware import get_current_user


class Classification(models.TextChoices):
    STAFF_ONLY = "staff_only", "Staff only"
    PUBLIC = "public", "Public"


class ApprovalState(models.TextChoices):
    PENDING = "pending", "Pending"
    UNDER_REVIEW = "under_review", "Under review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class DataSource(models.TextChoices):
    MIGRATED = "migrated", "Migrated from legacy data"
    AQUARIUS = "aquarius", "Aquarius Time-Series"
    HGA = "hga", "Hydro GeoAnalyst"
    SUBMISSION = "submission", "Data Submission application"
    API = "api", "API"
    STAFF = "staff", "Entered by WRA staff"


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditedModel(TimeStampedModel):
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", editable=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+", editable=False,
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()
        if user is not None and user.is_authenticated:
            if self._state.adding and self.created_by_id is None:
                self.created_by = user
            self.updated_by = user
        super().save(*args, **kwargs)


class PublishableModel(AuditedModel):
    """A record that goes through approval and carries an access classification.

    Nothing with approval_state != APPROVED is ever visible outside the review
    roles, and classification is applied at approval time (ToR H.ix–x).
    """

    approval_state = models.CharField(max_length=16, choices=ApprovalState.choices, default=ApprovalState.PENDING, db_index=True)
    classification = models.CharField(max_length=16, choices=Classification.choices, default=Classification.STAFF_ONLY, db_index=True)
    source = models.CharField(max_length=16, choices=DataSource.choices, default=DataSource.STAFF)
    paper_ref = models.CharField("Location of original paper records", max_length=255, blank=True)
    electronic_ref = models.CharField("Location of electronic records", max_length=255, blank=True)

    class Meta:
        abstract = True

    @property
    def is_public(self) -> bool:
        return self.approval_state == ApprovalState.APPROVED and self.classification == Classification.PUBLIC


class PublishedQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(approval_state=ApprovalState.APPROVED)

    def public(self):
        return self.approved().filter(classification=Classification.PUBLIC)

    def visible_to(self, user):
        """Public rows for guests/clients; approved rows for staff; everything for reviewers+."""
        if user is None or not user.is_authenticated or not user.is_staff_user:
            return self.public()
        if user.has_role("reviewer", "approver", "administrator"):
            return self
        return self.approved()


class AuditLog(models.Model):
    """Append-only. The database role used by the application has no UPDATE/DELETE
    grant on this table (see docs/security.md and scripts/db_roles.sql)."""

    at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_entries")
    action = models.CharField(max_length=64, db_index=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    target = GenericForeignKey("content_type", "object_id")
    summary = models.CharField(max_length=255, blank=True)
    meta = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=36, blank=True)

    class Meta:
        ordering = ["-at"]
        indexes = [models.Index(fields=["content_type", "object_id", "at"])]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} by {self.actor_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("AuditLog rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("AuditLog rows cannot be deleted")


class NotificationKind(models.TextChoices):
    WORKFLOW = "workflow", "Workflow stage update"
    LICENCE_EXPIRY = "licence_expiry", "Licence approaching expiry"
    LICENCE_EXPIRED = "licence_expired", "Licence expired"
    OVER_ABSTRACTION = "over_abstraction", "Abstraction above licensed volume"
    ACCOUNT = "account", "Account"
    SYSTEM = "system", "System"


class Notification(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=32, choices=NotificationKind.choices, default=NotificationKind.SYSTEM)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.CharField(max_length=255, blank=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "read_at"])]

    def __str__(self):
        return self.title
