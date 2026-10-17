"""Executive view (v0.13.0): read-only figures for the governance layer, plus milestone decisions by the approver of record."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import Milestone, MilestoneStatus


@login_required
def index(request):
    """The executive view."""
    if not services.can_view_executive(request.user):
        raise PermissionDenied
    ctx = {"licences": services.licence_figures(), "wmu": services.wmu_figures(), "backlog": services.backlog_by_branch(), "quality": services.quality_trend(),
           "adoption": services.adoption(), "ms": services.milestone_summary(), "can_decide": services.can_decide_milestones(request.user)}
    return render(request, "governance/index.html", ctx)


@login_required
@require_POST
def milestone_action(request, pk):
    """Accept, return or mark delivered — the approver of record only; everything audited."""
    if not services.can_decide_milestones(request.user):
        raise PermissionDenied
    m = get_object_or_404(Milestone, pk=pk)
    action = request.POST.get("action")
    remarks = request.POST.get("remarks", "").strip()
    if action == "accept":
        m.decide(request.user, True, remarks)
        messages.success(request, f"{m.code} {m.title} accepted on the Steering Committee's behalf.")
    elif action == "return":
        if not remarks:
            messages.error(request, "Say what needs to change before returning a milestone.")
            return redirect("governance:index")
        m.decide(request.user, False, remarks)
        messages.warning(request, f"{m.code} {m.title} returned for rework.")
    elif action == "delivered":
        m.mark_delivered(request.user, evidence_url=request.POST.get("evidence_url", "").strip())
        messages.success(request, f"{m.code} {m.title} recorded as delivered — awaiting acceptance.")
    elif action == "reopen":
        m.status = MilestoneStatus.PLANNED
        m.save(update_fields=["status", "updated_at"])
        messages.info(request, f"{m.code} set back to planned.")
    else:
        messages.error(request, "Unknown action.")
    return redirect("governance:index")
