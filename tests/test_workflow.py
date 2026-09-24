import pytest

from apps.workflow import engine
from apps.workflow.models import InstanceState, WorkflowDefinition


class Dummy:
    """Minimal subject: a Party stands in for any model."""


@pytest.mark.django_db
def test_full_chain_with_return_and_final_approval(party, client_user, reviewer, approver):
    inst = engine.start("data_submission_default", party, client_user, summary="test item")
    assert inst.current_stage.code == "review"
    with pytest.raises(engine.NotAuthorised):
        engine.approve(inst, client_user)
    engine.approve(inst, reviewer, "looks fine")
    inst.refresh_from_db()
    assert inst.current_stage.code == "approve"
    # approver returns to review
    review = inst.definition.stages.get(code="review")
    engine.return_to(inst, approver, review, "please re-check units")
    inst.refresh_from_db()
    assert inst.current_stage.code == "review" and inst.state == InstanceState.IN_PROGRESS
    engine.approve(inst, reviewer)
    engine.approve(inst, approver, "approved")
    inst.refresh_from_db()
    assert inst.state == InstanceState.APPROVED and inst.closed_at is not None
    actions = list(inst.actions.values_list("action", flat=True))
    assert actions == ["submit", "approve", "return", "approve", "final_approve"]


@pytest.mark.django_db
def test_reject_requires_reason_and_request_info_cycle(party, client_user, reviewer):
    inst = engine.start("data_submission_default", party, client_user, summary="x")
    with pytest.raises(engine.WorkflowError):
        engine.reject(inst, reviewer, "")
    engine.request_info(inst, reviewer, "need the lab report")
    inst.refresh_from_db()
    assert inst.state == InstanceState.INFO_REQUESTED
    with pytest.raises(engine.WorkflowError):
        engine.approve(inst, reviewer)
    engine.resubmit(inst, client_user, "attached")
    engine.reject(inst, reviewer, "out of scope")
    inst.refresh_from_db()
    assert inst.state == InstanceState.REJECTED


@pytest.mark.django_db
def test_actions_are_immutable(party, client_user):
    inst = engine.start("data_submission_default", party, client_user)
    a = inst.actions.first()
    a.comment = "edited"
    with pytest.raises(RuntimeError):
        a.save()
    with pytest.raises(RuntimeError):
        a.delete()


@pytest.mark.django_db
def test_notifications_created_for_stage_group_and_submitter(party, client_user, reviewer, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        engine.start("data_submission_default", party, client_user, summary="notify me")
    assert reviewer.notifications.filter(title__startswith="Awaiting your review").exists()
    assert client_user.notifications.filter(title__startswith="Received").exists()


@pytest.mark.django_db
def test_seeded_definitions_exist():
    assert WorkflowDefinition.objects.filter(code="licence_application").exists()
    assert WorkflowDefinition.objects.get(code="licence_application").stages.count() == 4
