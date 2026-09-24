"""
The workflow engine. Every public function:

* runs inside one database transaction with the subject row locked,
* checks the actor's authority against the stage's approver group,
* writes exactly one WorkflowAction and one AuditLog entry,
* emits notifications after commit (email + in-app, ToR H.xi),
* on final approval calls the subject's `on_workflow_approved(instance, actor)`
  hook (promotion of submitted data, licence issue, ...), and
  `on_workflow_rejected` / `on_workflow_info_requested` when defined.

Subjects register nothing: any model may be a workflow subject as long as the
hooks above exist. The subject is the single source of truth for business
state; the instance is the single source of truth for approval state.
"""
from __future__ import annotations

from dataclasses import dataclass

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.core import audit
from apps.core.models import NotificationKind
from apps.core.notifications import notify, notify_group

from .models import ActionType, InstanceState, WorkflowAction, WorkflowDefinition, WorkflowInstance, WorkflowStage


class WorkflowError(Exception):
    """Business-rule failure surfaced to the UI/API as a 400/422."""


class NotAuthorised(WorkflowError):
    pass


@dataclass
class Transition:
    instance: WorkflowInstance
    action: WorkflowAction


def _lock(instance: WorkflowInstance) -> WorkflowInstance:
    return WorkflowInstance.objects.select_for_update(of=("self",)).select_related("definition", "current_stage").get(pk=instance.pk)


def _require_open(instance):
    if not instance.is_open:
        raise WorkflowError(f"This item is closed ({instance.get_state_display()}).")


def _require_stage_actor(instance: WorkflowInstance, actor):
    stage = instance.current_stage
    if stage is None:
        raise WorkflowError("Item has no current stage.")
    if actor is None or not actor.is_authenticated:
        raise NotAuthorised("Sign in required.")
    if actor.is_superuser:
        return
    if not actor.groups.filter(pk=stage.approver_group_id).exists():
        raise NotAuthorised(f"Only members of '{stage.approver_group.name}' may act at stage '{stage.name}'.")


def _record(instance, action, actor, comment="", from_stage=None, to_stage=None, **meta) -> WorkflowAction:
    wa = WorkflowAction.objects.create(
        instance=instance, action=action, actor=actor if getattr(actor, "is_authenticated", False) else None,
        from_stage=from_stage, to_stage=to_stage, comment=comment, meta=meta,
    )
    audit.log(f"workflow.{action}", instance.subject, summary=f"{instance.summary} → {to_stage or instance.state}", actor=actor,
              instance=instance.pk, comment=comment[:500])
    return wa


def _notify_stage(instance: WorkflowInstance):
    stage = instance.current_stage
    if stage is None:
        return
    link = instance.subject.get_absolute_url() if hasattr(instance.subject, "get_absolute_url") else ""

    def _send():
        notify_group(stage.approver_group.name, f"Awaiting your review: {instance.summary}",
                     f"Stage: {stage.name}.", kind=NotificationKind.WORKFLOW, link=link, target=instance.subject)

    transaction.on_commit(_send)


def _notify_submitter(instance: WorkflowInstance, title: str, body: str = ""):
    if instance.submitter_id is None:
        return
    link = instance.subject.get_absolute_url() if hasattr(instance.subject, "get_absolute_url") else ""
    transaction.on_commit(lambda: notify(instance.submitter, title, body, kind=NotificationKind.WORKFLOW, link=link, target=instance.subject))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
@transaction.atomic
def start(definition: WorkflowDefinition | str, subject, submitter, summary: str = "") -> WorkflowInstance:
    if isinstance(definition, str):
        definition = WorkflowDefinition.objects.get(code=definition, is_active=True)
    first = definition.first_stage
    if first is None:
        raise WorkflowError(f"Workflow '{definition.code}' has no stages configured.")
    ct = ContentType.objects.get_for_model(subject)
    if WorkflowInstance.objects.filter(content_type=ct, object_id=str(subject.pk)).exists():
        raise WorkflowError("A workflow already exists for this item.")
    instance = WorkflowInstance.objects.create(
        definition=definition, current_stage=first, content_type=ct, object_id=str(subject.pk),
        submitter=submitter if getattr(submitter, "is_authenticated", False) else None, summary=summary[:200],
    )
    _record(instance, ActionType.SUBMIT, submitter, to_stage=first)
    _notify_stage(instance)
    _notify_submitter(instance, f"Received: {instance.summary}", f"Your item is now at stage '{first.name}'.")
    return instance


@transaction.atomic
def approve(instance: WorkflowInstance, actor, comment: str = "", **meta) -> Transition:
    instance = _lock(instance)
    _require_open(instance)
    if instance.state == InstanceState.INFO_REQUESTED:
        raise WorkflowError("Waiting on the submitter; cannot approve until resubmitted.")
    _require_stage_actor(instance, actor)
    stage = instance.current_stage
    nxt = stage.next_stage
    if nxt is not None:
        instance.current_stage = nxt
        instance.stage_entered_at = timezone.now()
        instance.save(update_fields=["current_stage", "stage_entered_at", "updated_at"])
        wa = _record(instance, ActionType.APPROVE, actor, comment, from_stage=stage, to_stage=nxt, **meta)
        _notify_stage(instance)
        _notify_submitter(instance, f"Progressed: {instance.summary}", f"Now at stage '{nxt.name}'.")
        return Transition(instance, wa)
    # final approval
    instance.state = InstanceState.APPROVED
    instance.closed_at = timezone.now()
    instance.save(update_fields=["state", "closed_at", "updated_at"])
    wa = _record(instance, ActionType.FINAL_APPROVE, actor, comment, from_stage=stage, **meta)
    hook = getattr(instance.subject, "on_workflow_approved", None)
    if hook is not None:
        hook(instance, actor, **meta)
    _notify_submitter(instance, f"Approved: {instance.summary}", comment)
    return Transition(instance, wa)


@transaction.atomic
def reject(instance: WorkflowInstance, actor, comment: str) -> Transition:
    instance = _lock(instance)
    _require_open(instance)
    _require_stage_actor(instance, actor)
    if not instance.current_stage.can_reject:
        raise WorkflowError("This stage cannot reject; return the item instead.")
    if not comment.strip():
        raise WorkflowError("A reason is required to reject.")
    stage = instance.current_stage
    instance.state = InstanceState.REJECTED
    instance.closed_at = timezone.now()
    instance.save(update_fields=["state", "closed_at", "updated_at"])
    wa = _record(instance, ActionType.REJECT, actor, comment, from_stage=stage)
    hook = getattr(instance.subject, "on_workflow_rejected", None)
    if hook is not None:
        hook(instance, actor, comment)
    _notify_submitter(instance, f"Not approved: {instance.summary}", comment)
    return Transition(instance, wa)


@transaction.atomic
def return_to(instance: WorkflowInstance, actor, target: WorkflowStage, comment: str) -> Transition:
    """Return to an earlier stage for correction/clarification (ToR G.1.v)."""
    instance = _lock(instance)
    _require_open(instance)
    _require_stage_actor(instance, actor)
    stage = instance.current_stage
    if not stage.can_return_to.filter(pk=target.pk).exists():
        raise WorkflowError(f"Stage '{stage.name}' may not return items to '{target.name}'.")
    if not comment.strip():
        raise WorkflowError("A reason is required to return an item.")
    instance.current_stage = target
    instance.stage_entered_at = timezone.now()
    instance.state = InstanceState.IN_PROGRESS
    instance.save(update_fields=["current_stage", "stage_entered_at", "state", "updated_at"])
    wa = _record(instance, ActionType.RETURN, actor, comment, from_stage=stage, to_stage=target)
    _notify_stage(instance)
    return Transition(instance, wa)


@transaction.atomic
def request_info(instance: WorkflowInstance, actor, comment: str) -> Transition:
    instance = _lock(instance)
    _require_open(instance)
    _require_stage_actor(instance, actor)
    if not instance.current_stage.can_return_to_submitter:
        raise WorkflowError("This stage cannot send the item back to the submitter.")
    if not comment.strip():
        raise WorkflowError("Tell the submitter what is needed.")
    instance.state = InstanceState.INFO_REQUESTED
    instance.save(update_fields=["state", "updated_at"])
    wa = _record(instance, ActionType.REQUEST_INFO, actor, comment, from_stage=instance.current_stage)
    hook = getattr(instance.subject, "on_workflow_info_requested", None)
    if hook is not None:
        hook(instance, actor, comment)
    _notify_submitter(instance, f"Information needed: {instance.summary}", comment)
    return Transition(instance, wa)


@transaction.atomic
def resubmit(instance: WorkflowInstance, actor, comment: str = "") -> Transition:
    instance = _lock(instance)
    if instance.state != InstanceState.INFO_REQUESTED:
        raise WorkflowError("Nothing to resubmit.")
    if actor.pk != instance.submitter_id and not actor.is_superuser:
        raise NotAuthorised("Only the submitter may resubmit.")
    instance.state = InstanceState.IN_PROGRESS
    instance.stage_entered_at = timezone.now()
    instance.save(update_fields=["state", "stage_entered_at", "updated_at"])
    wa = _record(instance, ActionType.RESUBMIT, actor, comment, to_stage=instance.current_stage)
    _notify_stage(instance)
    return Transition(instance, wa)


@transaction.atomic
def withdraw(instance: WorkflowInstance, actor, comment: str = "") -> Transition:
    instance = _lock(instance)
    _require_open(instance)
    if not instance.definition.allow_submitter_withdraw:
        raise WorkflowError("Withdrawal is not permitted for this workflow.")
    if actor.pk != instance.submitter_id and not actor.is_superuser:
        raise NotAuthorised("Only the submitter may withdraw.")
    instance.state = InstanceState.WITHDRAWN
    instance.closed_at = timezone.now()
    instance.save(update_fields=["state", "closed_at", "updated_at"])
    wa = _record(instance, ActionType.WITHDRAW, actor, comment, from_stage=instance.current_stage)
    return Transition(instance, wa)


@transaction.atomic
def comment(instance: WorkflowInstance, actor, text: str) -> WorkflowAction:
    instance = _lock(instance)
    if not text.strip():
        raise WorkflowError("Empty comment.")
    return _record(instance, ActionType.COMMENT, actor, text, from_stage=instance.current_stage)


def queue_for(user):
    """Open items at stages whose approver group the user belongs to."""
    if user.is_superuser:
        return WorkflowInstance.objects.filter(state=InstanceState.IN_PROGRESS)
    return WorkflowInstance.objects.filter(state=InstanceState.IN_PROGRESS, current_stage__approver_group__in=user.groups.all())


def instance_for(subject) -> WorkflowInstance | None:
    ct = ContentType.objects.get_for_model(subject)
    return WorkflowInstance.objects.filter(content_type=ct, object_id=str(subject.pk)).select_related("current_stage", "definition").first()
