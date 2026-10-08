"""Unit console services: raise cleansing issues from profiler results; unit overview figures (v0.8.0)."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Unit
from apps.accounts.ownership import unit_may_act

from .models import CleansingIssue, IssueKind, IssueStatus


def issues_from_profile(profile, unit: Unit, source: str | None = None) -> list[CleansingIssue]:
    """Turn a :class:`apps.core.profiling.FileProfile` into cleansing issues for ``unit`` (one per finding; idempotent per source+column+kind)."""
    source = source or profile.path
    made = []

    def add(kind, column, summary, details, rows=0):
        obj, created = CleansingIssue.objects.get_or_create(
            unit=unit, source=source, column=column, kind=kind, status=IssueStatus.OPEN,
            defaults={"summary": summary[:300], "details": details, "rows_affected": rows})
        if created:
            made.append(obj)

    if profile.duplicate_rows:
        add(IssueKind.DUPLICATE, "", f"{profile.duplicate_rows} fully duplicated row(s) in {source}", {"duplicate_rows": profile.duplicate_rows}, profile.duplicate_rows)
    if profile.encoding not in ("utf-8", "utf-8-sig", "xlsx"):
        add(IssueKind.ENCODING, "", f"{source} is not UTF-8 ({profile.encoding}); accented names will need re-encoding", {"encoding": profile.encoding})
    for c in profile.columns:
        if c.reference_match and c.reference_match.get("match_pct", 100) < 95:
            rm = c.reference_match
            add(IssueKind.UNMATCHED, c.name, f"Column '{c.name}': {rm['unmatched']} value(s) match no reference record ({rm['match_pct']}% matched)",
                {"match": rm, "top_unmatched": rm.get("top_unmatched", [])}, sum(n for _, n in rm.get("top_unmatched", [])))
        if c.inferred == "mixed":
            add(IssueKind.MIXED_TYPES, c.name, f"Column '{c.name}' mixes types", {"types": dict(c.types), "examples": c.examples[:5]})
        if len(c.date_formats) > 1:
            add(IssueKind.DATE_FORMATS, c.name, f"Column '{c.name}' uses {len(c.date_formats)} date formats", {"formats": dict(c.date_formats)})
        if c.null_tokens:
            add(IssueKind.PLACEHOLDER, c.name, f"Column '{c.name}' uses placeholder blanks", {"tokens": dict(c.null_tokens.most_common(5))}, sum(c.null_tokens.values()))
        if c.numeric_outliers:
            add(IssueKind.OUT_OF_RANGE, c.name, f"Column '{c.name}': {c.numeric_outliers} value(s) far outside the usual range",
                {"min": c.numeric_min, "max": c.numeric_max, "mean": c.numeric_mean, "outliers": c.numeric_outliers}, c.numeric_outliers)
    return made


def unit_for_source(source_hint: str) -> Unit | None:
    """Guess the owning unit from a file name (licence/abstraction → PLU, basin/wmu/model → PIU, else RMU)."""
    s = source_hint.lower()
    code = "PLU" if any(k in s for k in ("licen", "abstract", "permit")) else "PIU" if any(k in s for k in ("basin", "wmu", "aquifer", "model")) else "RMU"
    return Unit.objects.filter(code=code).first()


# -- overview ----------------------------------------------------------------------------------


def open_items(unit: Unit):
    """Open workflow items the unit may act on, with an overdue flag from the stage's SLA."""
    from apps.workflow.models import InstanceState, WorkflowInstance

    probe = unit.members.filter(is_active=True).first()
    qs = WorkflowInstance.objects.filter(state__in=[InstanceState.IN_PROGRESS, InstanceState.INFO_REQUESTED]).select_related("current_stage", "definition", "submitter")
    rows = []
    now = timezone.now()
    for inst in qs:
        owner_ok = unit_may_act(probe, inst)[0] if probe else False
        stage = inst.current_stage
        if not owner_ok or stage is None:
            continue
        if not (stage.owning_unit_id == unit.pk or (stage.owning_unit_id is None and getattr(inst.subject, "owning_unit", None) == unit)):
            continue
        sla = stage.sla_days
        age = (now - inst.stage_entered_at).days
        rows.append({"instance": inst, "age_days": age, "sla_days": sla, "overdue": bool(sla) and age > sla, "waiting": inst.state == InstanceState.INFO_REQUESTED})
    rows.sort(key=lambda r: (-int(r["overdue"]), -r["age_days"]))
    return rows


def support_summary(unit: Unit):
    """Sign-in trouble for the unit's people in the last 7 days, plus who is locked out right now (django-axes)."""
    from axes.models import AccessAttempt, AccessFailureLog
    from django_otp.plugins.otp_totp.models import TOTPDevice

    members = list(unit.members.filter(is_active=True).order_by("full_name"))
    emails = [m.email for m in members]
    since = timezone.now() - timedelta(days=7)
    failures = AccessFailureLog.objects.filter(username__in=emails, attempt_time__gte=since).order_by("-attempt_time")[:50]
    limit = settings.AXES_FAILURE_LIMIT
    cooloff = settings.AXES_COOLOFF_TIME
    locked = set()
    for a in AccessAttempt.objects.filter(username__in=emails, failures_since_start__gte=limit):
        if a.attempt_time >= timezone.now() - cooloff:
            locked.add(a.username)
    enrolled = set(TOTPDevice.objects.filter(user__in=members, confirmed=True).values_list("user_id", flat=True))
    people = [{"user": m, "roles": ", ".join(g.name for g in m.groups.all()), "mfa": m.pk in enrolled, "mfa_required": m.mfa_required, "locked": m.email in locked}
              for m in members]
    return {"people": people, "failures": list(failures), "locked": sorted(locked)}


def can_run_console(user, unit: Unit | None = None) -> bool:
    """Super Users for their own unit; superusers and administrators for any unit."""
    if not getattr(user, "is_authenticated", False) or not user.is_staff_user:
        return False
    if user.is_superuser or user.has_role("administrator"):
        return True
    return bool(user.is_super_user and user.unit_id and (unit is None or user.unit_id == unit.pk))


def units_for(user):
    """Units the user may open the console for."""
    if user.is_superuser or user.has_role("administrator"):
        return Unit.objects.filter(is_active=True).filter(Q(is_operating=True) | Q(has_super_user=True))
    return Unit.objects.filter(pk=user.unit_id) if user.unit_id else Unit.objects.none()
