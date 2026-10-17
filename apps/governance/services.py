"""Figures for the executive view (v0.13.0): licences, WMU utilisation, backlog by branch, data-quality trend, adoption, milestones."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone

from apps.accounts.models import Unit

ICT_UNIT = "CGU"  # Computer & GIS Unit — the ICT Manager, approver of record
EXEC_UNITS = {"MDO", ICT_UNIT}


def can_view_executive(user) -> bool:
    """The governance layer (Managing Director's Office, Computer & GIS Unit), administrators, BI analysts and superusers."""
    if not getattr(user, "is_authenticated", False) or not user.is_staff_user:
        return False
    return user.is_superuser or user.has_role("administrator", "bi_analyst") or (user.unit_id is not None and user.unit.code in EXEC_UNITS)


def can_decide_milestones(user) -> bool:
    """The approver of record: an administrator in the Computer & GIS Unit (ICT Manager), or a superuser."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.is_superuser or (user.unit_id is not None and user.unit.code == ICT_UNIT and user.has_role("administrator"))


def licence_figures() -> dict:
    """Licences issued this year and active overall; applications in progress and decided in the last 90 days."""
    from apps.lic.models import ApplicationStatus, Licence, LicenceApplication, LicenceStatus

    today = timezone.localdate()
    year_start = today.replace(month=1, day=1)
    issued = Licence.objects.filter(issued_on__gte=year_start)
    active = Licence.objects.filter(status=LicenceStatus.ACTIVE)
    since = today - timedelta(days=90)
    decided = LicenceApplication.objects.filter(decided_at__date__gte=since)
    return {
        "issued_year": issued.count(), "issued_year_volume": float(issued.aggregate(v=Sum("daily_volume_granted_m3"))["v"] or 0),
        "active": active.count(), "active_volume": float(active.aggregate(v=Sum("daily_volume_granted_m3"))["v"] or 0),
        "in_progress": LicenceApplication.objects.filter(status__in=[ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INFO_REQUESTED]).count(),
        "granted_90": decided.filter(status=ApplicationStatus.GRANTED).count(), "refused_90": decided.filter(status=ApplicationStatus.REFUSED).count(),
        "expiring_90": active.filter(expires_on__lte=today + timedelta(days=90)).count(),
    }


def wmu_figures() -> dict:
    """How many WMUs sit in each utilisation band, and the ones over 85 %."""
    from apps.lic.services import wmu_balance
    from apps.ref.models import WMU

    bands = {"under_60": 0, "b60_85": 0, "b85_100": 0, "over_100": 0, "no_yield": 0}
    hot = []
    for w in WMU.objects.select_related("basin"):
        b = wmu_balance(w)
        u = b["utilisation_with_pending_pct"] if b["utilisation_with_pending_pct"] is not None else b["utilisation_pct"]
        if u is None:
            bands["no_yield"] += 1
        elif u > 100:
            bands["over_100"] += 1
        elif u > 85:
            bands["b85_100"] += 1
        elif u > 60:
            bands["b60_85"] += 1
        else:
            bands["under_60"] += 1
        if u is not None and u > 85:
            hot.append({"code": w.code, "name": w.name, "basin": w.basin.name if w.basin_id else "", "pct": u, "licences": b["licences"]})
    hot.sort(key=lambda r: -r["pct"])
    return {"bands": bands, "total": sum(bands.values()), "hot": hot}


def backlog_by_branch() -> list[dict]:
    """Open workflow items per operating unit, with how many are past their stage SLA and the oldest age."""
    from apps.console.services import open_items

    rows = []
    for unit in Unit.objects.filter(is_operating=True).order_by("name"):
        items = open_items(unit)
        rows.append({"unit": unit, "open": len(items), "overdue": sum(1 for i in items if i["overdue"]), "waiting": sum(1 for i in items if i["waiting"]),
                     "oldest_days": max((i["age_days"] for i in items), default=0)})
    return rows


def quality_trend() -> dict:
    """Flagged share of submitted rows, last 30 days against the 30 before; cleansing issues open and resolved."""
    from apps.console.models import CleansingIssue, IssueStatus
    from apps.submissions.models import Submission

    now = timezone.now()
    mid, start = now - timedelta(days=30), now - timedelta(days=60)

    def share(qs):
        agg = qs.aggregate(rows=Sum("row_count"), flagged=Sum("flagged_count"))
        rows = agg["rows"] or 0
        return {"rows": rows, "flagged": agg["flagged"] or 0, "pct": round((agg["flagged"] or 0) * 100 / rows, 1) if rows else None, "submissions": qs.count()}

    recent = share(Submission.objects.filter(created_at__gte=mid))
    before = share(Submission.objects.filter(created_at__gte=start, created_at__lt=mid))
    issues = CleansingIssue.objects.values("status").annotate(n=Count("id"))
    by_status = {r["status"]: r["n"] for r in issues}
    open_n = by_status.get(IssueStatus.OPEN, 0)
    resolved_n = by_status.get(IssueStatus.RESOLVED, 0)
    direction = None
    if recent["pct"] is not None and before["pct"] is not None:
        direction = "better" if recent["pct"] < before["pct"] else "worse" if recent["pct"] > before["pct"] else "same"
    return {"recent": recent, "before": before, "direction": direction, "issues_open": open_n, "issues_resolved": resolved_n,
            "issues_resolved_30": CleansingIssue.objects.filter(status=IssueStatus.RESOLVED, decided_at__gte=mid).count()}


def adoption() -> list[dict]:
    """Latest adoption sign-off per unit that holds a Super User."""
    from apps.console.models import ADOPTION_MEASURES, AdoptionSignoff

    rows = []
    for unit in Unit.objects.filter(has_super_user=True).order_by("name"):
        s = AdoptionSignoff.objects.filter(unit=unit).select_related("signed_by").first()
        met = sum(1 for code, _ in ADOPTION_MEASURES if s and s.measures.get(code)) if s else 0
        rows.append({"unit": unit, "signoff": s, "met": met, "of": len(ADOPTION_MEASURES)})
    return rows


def milestone_summary() -> dict:
    """Counts by status and the next milestone due."""
    from apps.governance.models import Milestone, MilestoneStatus

    qs = Milestone.objects.all()
    counts = {s: 0 for s, _ in MilestoneStatus.choices}
    for r in qs.values("status").annotate(n=Count("id")):
        counts[r["status"]] = r["n"]
    nxt = qs.exclude(status=MilestoneStatus.ACCEPTED).order_by("number").first()
    return {"counts": counts, "total": qs.count(), "next": nxt, "milestones": list(qs.select_related("decided_by"))}
