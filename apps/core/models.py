"""Core building blocks shared by every app.

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
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from .middleware import get_current_user


class Classification(models.TextChoices):
    """Access classification applied at approval (ToR H.x)."""
    STAFF_ONLY = "staff_only", "Staff only"
    PUBLIC = "public", "Public"


class ApprovalState(models.TextChoices):
    """Life-cycle of a record: pending (working) → under review → approved / rejected (ToR H.ix)."""
    PENDING = "pending", "Pending"
    UNDER_REVIEW = "under_review", "Under review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class DataSource(models.TextChoices):
    """Where a record came from (migration, integration, submission, staff)."""
    MIGRATED = "migrated", "Migrated from legacy data"
    AQUARIUS = "aquarius", "Aquarius Time-Series"
    HGA = "hga", "Hydro GeoAnalyst"
    SUBMISSION = "submission", "Data Submission application"
    API = "api", "API"
    STAFF = "staff", "Entered by WRA staff"


class TimeStampedModel(models.Model):
    """``created_at`` / ``updated_at`` on every table."""
    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditedModel(TimeStampedModel):
    """Timestamps plus ``created_by`` / ``updated_by`` filled from the request."""
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
        """Stamp the acting user before saving."""
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
        """True when approved and classified public."""
        return self.approval_state == ApprovalState.APPROVED and self.classification == Classification.PUBLIC


class ObservationGrade(models.TextChoices):
    """Quality grade of a single observation (design doc 14 §3.2).

    Mirrors the grade scale WRA already uses in Aquarius Time-Series so migrated
    values keep their grade. ``ESTIMATED`` and ``MISSING`` are grades, not
    qualifiers: an estimated value is still a value, a missing one is a
    placeholder row that keeps the series continuous.
    """

    UNGRADED = "", "Ungraded"
    GOOD = "good", "Good"
    FAIR = "fair", "Fair"
    POOR = "poor", "Poor"
    ESTIMATED = "estimated", "Estimated"
    MISSING = "missing", "Missing"


class QualityMixin(models.Model):
    """Grade and qualifier columns shared by every observation table.

    ``approval_state`` (on PublishableModel) carries the working → in review →
    approved life-cycle the hydrologists asked for; the ToR's ``pending`` and
    ``under_review`` map onto "working" and "in review" so one state machine
    serves both submitted and staff-entered data (ADR-0001).

    Qualifier codes come from ``ref.Qualifier`` (e.g. ``ICE``, ``PUMPING``,
    ``EQUIP``) and are stored denormalised as text so a row stays readable in
    exports and in Metabase without a join.
    """

    grade = models.CharField(max_length=10, choices=ObservationGrade.choices, default=ObservationGrade.UNGRADED, blank=True, db_index=True)
    qualifiers = ArrayField(models.CharField(max_length=16), default=list, blank=True, help_text="Qualifier codes from ref.Qualifier, e.g. ['PUMPING']")
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False,
    )
    graded_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    @property
    def is_estimated(self) -> bool:
        """True when the value was estimated or gap-filled rather than measured."""
        return self.grade == ObservationGrade.ESTIMATED

    def set_grade(self, grade: str, qualifiers: list[str] | None = None, user=None) -> None:
        """Record a grade (and optional qualifiers) with who/when, without saving."""
        self.grade = grade
        if qualifiers is not None:
            self.qualifiers = sorted(set(qualifiers))
        self.graded_by = user
        self.graded_at = timezone.now()


class PublishedQuerySet(models.QuerySet):
    """Queryset helpers that enforce approval state and classification."""
    def approved(self):
        """Approved rows only."""
        return self.filter(approval_state=ApprovalState.APPROVED)

    def public(self):
        """Approved and public rows only."""
        return self.approved().filter(classification=Classification.PUBLIC)

    def visible_to(self, user):
        """Public rows for guests/clients; approved rows for staff; everything for reviewers+."""
        if user is None or not user.is_authenticated or not user.is_staff_user:
            return self.public()
        from apps.accounts import roles

        if user.has_role(*roles.UNAPPROVED_DATA_ROLES):
            return self
        return self.approved()


class AuditLog(models.Model):
    """Append-only audit entry (ToR H.xvi, F.5).

    The database role used by the application has no UPDATE/DELETE grant on this
    table (see docs/security.md and scripts/db_roles.sql).
    """

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
        """Insert only; updating an audit row raises."""
        if not self._state.adding:
            raise RuntimeError("AuditLog rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        """Audit rows cannot be deleted."""
        raise RuntimeError("AuditLog rows cannot be deleted")


class NotificationKind(models.TextChoices):
    """What a notification is about."""
    WORKFLOW = "workflow", "Workflow stage update"
    LICENCE_EXPIRY = "licence_expiry", "Licence approaching expiry"
    LICENCE_EXPIRED = "licence_expired", "Licence expired"
    OVER_ABSTRACTION = "over_abstraction", "Abstraction above licensed volume"
    ACCOUNT = "account", "Account"
    SYSTEM = "system", "System"


class Notification(TimeStampedModel):
    """In-app notification; the email copy is sent by a task (ToR H.xi)."""
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
