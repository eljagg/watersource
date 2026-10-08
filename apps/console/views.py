"""Unit console views (v0.8.0): overview, cleansing queue decisions, account unlock, adoption sign-off."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Unit, User
from apps.core.audit import log

from . import services
from .models import ADOPTION_MEASURES, AdoptionSignoff, CleansingIssue, Decision, IssueStatus


def _unit(request) -> Unit:
    units = services.units_for(request.user)
    code = request.GET.get("unit") or request.POST.get("unit")
    unit = units.filter(code=code).first() if code else (units.filter(pk=request.user.unit_id).first() or units.first())
    if unit is None or not services.can_run_console(request.user, unit):
        raise Http404
    return unit


@login_required
def index(request):
    """The Super User's desk for one unit."""
    if not services.can_run_console(request.user):
        raise Http404
    unit = _unit(request)
    issues = CleansingIssue.objects.filter(unit=unit).select_related("decided_by")
    open_issues = [i for i in issues if i.status == IssueStatus.OPEN]
    resolved = [i for i in issues if i.status == IssueStatus.RESOLVED][:20]
    items = services.open_items(unit)
    signoff = AdoptionSignoff.objects.filter(unit=unit).select_related("signed_by").first()
    return render(request, "console/index.html", {
        "unit": unit, "units": services.units_for(request.user), "items": items, "overdue": sum(1 for r in items if r["overdue"]),
        "open_issues": open_issues, "resolved_issues": resolved, "decisions": Decision.choices, "support": services.support_summary(unit),
        "signoff": signoff, "measures": ADOPTION_MEASURES, "can_sign": request.user.is_super_user and request.user.unit_id == unit.pk or request.user.is_superuser,
    })


@login_required
@require_POST
def resolve(request, pk):
    """Record a decision on a cleansing issue."""
    issue = get_object_or_404(CleansingIssue, pk=pk, status=IssueStatus.OPEN)
    if not services.can_run_console(request.user, issue.unit):
        raise Http404
    decision = request.POST.get("decision")
    if decision not in Decision.values:
        messages.error(request, "Choose a decision.")
    else:
        note = request.POST.get("note", "").strip()
        target = request.POST.get("target", "").strip()
        if decision == Decision.MAP and not target:
            messages.error(request, "Say which record the value maps to.")
        else:
            issue.resolve(request.user, decision, note, target)
            messages.success(request, f"Decision recorded: {issue.get_decision_display()}.")
    return redirect(f"/unit/?unit={issue.unit.code}#cleansing")


@login_required
@require_POST
def unlock(request, pk):
    """Clear a locked-out member's failed sign-in counter (first-line support)."""
    from axes.utils import reset

    member = get_object_or_404(User, pk=pk)
    if member.unit_id is None or not services.can_run_console(request.user, member.unit):
        raise Http404
    n = reset(username=member.email)
    log("auth.unlocked", target=member, summary=f"Sign-in lock cleared for {member.email} by the unit console ({n} record(s))", actor=request.user)
    messages.success(request, f"{member.full_name} can sign in again.")
    return redirect(f"/unit/?unit={member.unit.code}#support")


@login_required
@require_POST
def signoff(request):
    """Record the unit's adoption sign-off (Work Plan M17)."""
    unit = _unit(request)
    if not (request.user.is_superuser or (request.user.is_super_user and request.user.unit_id == unit.pk)):
        raise Http404
    measures = {code: request.POST.get(f"m_{code}") == "on" for code, _ in ADOPTION_MEASURES}
    s = AdoptionSignoff.objects.create(unit=unit, signed_by=request.user, measures=measures, statement=request.POST.get("statement", "").strip())
    log("adoption.signed", target=s, summary=f"{unit.code}: {sum(measures.values())}/{len(measures)} measures confirmed", actor=request.user)
    messages.success(request, "Adoption sign-off recorded." if s.complete else "Sign-off recorded with outstanding measures — it shows as partial until all are confirmed.")
    return redirect(f"/unit/?unit={unit.code}#adoption")
