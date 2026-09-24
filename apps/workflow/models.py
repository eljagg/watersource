"""
Configurable multi-level approval workflow (ToR H.viii, F.viii, G.1.iv–v).

A WorkflowDefinition is an ordered list of stages, each bound to an approver
group. The engine (engine.py) moves a WorkflowInstance between stages and
records every action in WorkflowAction inside the same transaction as the
state change (ToR H.xvi). Stage counts, roles and sequencing are data that a
WRA administrator edits; they are finalised in the initiation workshops.
"""
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class WorkflowDefinition(TimeStampedModel):
    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    allow_submitter_withdraw = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def ordered_stages(self):
        return list(self.stages.order_by("order"))

    @property
    def first_stage(self):
        return self.stages.order_by("order").first()


class WorkflowStage(models.Model):
    definition = models.ForeignKey(WorkflowDefinition, on_delete=models.CASCADE, related_name="stages")
    order = models.PositiveSmallIntegerField()
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=150)
    approver_group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="workflow_stages")
    can_return_to = models.ManyToManyField("self", symmetrical=False, blank=True, related_name="returnable_from",
                                           help_text="Earlier stages this stage may return an item to.")
    can_return_to_submitter = models.BooleanField(default=True, help_text="Allow 'request information' back to the submitter.")
    can_reject = models.BooleanField(default=True)
    sla_days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Target turnaround for reporting.")
    instructions = models.TextField(blank=True, help_text="Shown to the approver on the review screen.")

    class Meta:
        ordering = ["definition", "order"]
        constraints = [
            models.UniqueConstraint(fields=["definition", "order"], name="uq_stage_order"),
            models.UniqueConstraint(fields=["definition", "code"], name="uq_stage_code"),
        ]

    def __str__(self):
        return f"{self.definition.code}/{self.order} {self.name}"

    @property
    def next_stage(self):
        return self.definition.stages.filter(order__gt=self.order).order_by("order").first()

    @property
    def is_final(self):
        return self.next_stage is None


class InstanceState(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    INFO_REQUESTED = "info_requested", "Information requested from submitter"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    WITHDRAWN = "withdrawn", "Withdrawn"


class WorkflowInstance(TimeStampedModel):
    definition = models.ForeignKey(WorkflowDefinition, on_delete=models.PROTECT, related_name="instances")
    current_stage = models.ForeignKey(WorkflowStage, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    state = models.CharField(max_length=16, choices=InstanceState.choices, default=InstanceState.IN_PROGRESS, db_index=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    subject = GenericForeignKey("content_type", "object_id")
    submitter = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="submitted_workflows")
    started_at = models.DateTimeField(default=timezone.now)
    stage_entered_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    summary = models.CharField(max_length=200, blank=True, help_text="Shown in queues: e.g. 'WRA-LA-2026-000123 · J. Brown · St. Catherine'")

    class Meta:
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["state", "current_stage"]),
        ]
        constraints = [models.UniqueConstraint(fields=["content_type", "object_id"], name="uq_workflow_subject")]

    def __str__(self):
        return f"{self.definition.code} #{self.pk} [{self.state}]"

    @property
    def is_open(self):
        return self.state in (InstanceState.IN_PROGRESS, InstanceState.INFO_REQUESTED)


class ActionType(models.TextChoices):
    SUBMIT = "submit", "Submitted"
    APPROVE = "approve", "Approved (advanced to next stage)"
    FINAL_APPROVE = "final_approve", "Final approval"
    REJECT = "reject", "Rejected"
    RETURN = "return", "Returned to earlier stage"
    REQUEST_INFO = "request_info", "Information requested from submitter"
    RESUBMIT = "resubmit", "Resubmitted"
    WITHDRAW = "withdraw", "Withdrawn"
    COMMENT = "comment", "Comment"
    CLASSIFY = "classify", "Access classification set"


class WorkflowAction(models.Model):
    """Append-only log of every workflow action (ToR H.xvi)."""

    instance = models.ForeignKey(WorkflowInstance, on_delete=models.CASCADE, related_name="actions")
    action = models.CharField(max_length=16, choices=ActionType.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="workflow_actions")
    from_stage = models.ForeignKey(WorkflowStage, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    to_stage = models.ForeignKey(WorkflowStage, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    comment = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["at", "pk"]

    def __str__(self):
        return f"{self.at:%Y-%m-%d %H:%M} {self.action} by {self.actor_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("WorkflowAction rows are immutable")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("WorkflowAction rows cannot be deleted")
