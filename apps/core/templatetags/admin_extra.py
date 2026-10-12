"""Admin console home panel (v0.11.1): who is signed in, recent sign-ins, lock-outs, latest audit entries, key counts."""
from __future__ import annotations

import re
from datetime import timedelta

from django import template
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Max
from django.utils import timezone

register = template.Library()

BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Chrome/", "Chrome"), ("Firefox/", "Firefox"), ("Safari/", "Safari"))
PLATFORMS = (("Windows", "Windows"), ("Mac OS X", "macOS"), ("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Linux", "Linux"))


def browser(ua: str) -> str:
    """'Chrome on Windows' from a user-agent string."""
    ua = ua or ""
    b = next((name for key, name in BROWSERS if key in ua), "Browser")
    p = next((name for key, name in PLATFORMS if key in ua), "")
    return f"{b} on {p}" if p else b


def _ago(dt):
    s = int((timezone.now() - dt).total_seconds())
    if s < 60:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if s >= size:
            n = s // size
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


@register.inclusion_tag("admin/_activity.html")
def admin_activity():
    """Everything the panel shows; each block fails soft so the admin home always renders."""
    from axes.models import AccessAttempt, AccessLog

    from apps.core.models import AuditLog, RecentView
    from apps.workflow.models import InstanceState, WorkflowInstance

    User = get_user_model()
    now = timezone.now()
    idle = timedelta(minutes=settings.SESSION_IDLE_MINUTES)
    absolute = timedelta(seconds=settings.SESSION_COOKIE_AGE)
    users = {u.email: u for u in User.objects.select_related("unit").prefetch_related("groups")}
    last_seen = {r["user__email"]: r["at"] for r in RecentView.objects.values("user__email").annotate(at=Max("at"))}

    online, seen_names = [], set()
    for log in AccessLog.objects.filter(logout_time__isnull=True, attempt_time__gte=now - absolute).order_by("-attempt_time"):
        if log.username in seen_names:
            continue
        seen_names.add(log.username)
        u = users.get(log.username)
        active = max([t for t in (log.attempt_time, last_seen.get(log.username)) if t])
        unit = u.unit.name if u and u.unit_id else ("Client" if u and not u.is_staff_user else "")
        online.append({"name": u.full_name if u else log.username, "email": log.username, "unit": unit,
                       "roles": ", ".join(g.name for g in u.groups.all()) if u else "", "ip": log.ip_address, "browser": browser(log.user_agent),
                       "signed_in": log.attempt_time, "active": active, "active_ago": _ago(active), "status": "active" if now - active <= idle else "idle"})

    signins = [{"name": users[e.username].full_name if e.username in users else e.username, "email": e.username, "ip": e.ip_address,
                "browser": browser(e.user_agent), "at": e.attempt_time, "ago": _ago(e.attempt_time), "out": e.logout_time,
                "expired": e.logout_time is None and now - e.attempt_time > absolute}
               for e in AccessLog.objects.filter(attempt_time__gte=now - timedelta(days=7)).order_by("-attempt_time")[:12]]

    locked = [{"email": a.username, "failures": a.failures_since_start, "at": a.attempt_time, "ago": _ago(a.attempt_time), "ip": a.ip_address}
              for a in AccessAttempt.objects.filter(failures_since_start__gte=settings.AXES_FAILURE_LIMIT,
                                                    attempt_time__gte=now - settings.AXES_COOLOFF_TIME).order_by("-attempt_time")]

    audit = [{"at": e.at, "ago": _ago(e.at), "actor": e.actor.full_name if e.actor_id else "system", "action": e.action, "summary": e.summary}
             for e in AuditLog.objects.select_related("actor").order_by("-at")[:12]]

    staff = User.objects.filter(user_type="staff", is_active=True).count()
    counts = {"staff": staff, "clients": User.objects.filter(is_active=True).exclude(user_type="staff").count(), "online": len(online), "locked": len(locked),
              "open_items": WorkflowInstance.objects.filter(state=InstanceState.IN_PROGRESS).count(),
              "signins_24h": AccessLog.objects.filter(attempt_time__gte=now - timedelta(hours=24)).count()}
    try:
        from apps.maps.models import WraFeature

        wra = WraFeature.objects.aggregate(n=Max("fetched_at"))["n"]
        counts["wra_layers"] = WraFeature.objects.values("layer").distinct().count()
        counts["wra_fetched"] = _ago(wra) if wra else "never"
    except Exception:  # pragma: no cover - table missing during migration
        counts["wra_layers"], counts["wra_fetched"] = 0, "never"
    return {"online": online, "signins": signins, "locked": locked, "audit": audit, "counts": counts, "idle_minutes": settings.SESSION_IDLE_MINUTES}


@register.filter
def short_action(value: str) -> str:
    """'licence.application_submitted' → 'Licence · application submitted'."""
    if not value or "." not in value:
        return value
    a, b = value.split(".", 1)
    return f"{a.capitalize()} · {re.sub('_', ' ', b)}"
