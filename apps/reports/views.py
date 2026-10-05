"""Dashboard pages, the JSON they read, and the wall display (design doc 13 §3, §6).

* ``/dashboards/<slug>/`` — desk view inside the normal site chrome (staff only).
* ``/dashboards/<slug>/data/`` — the panel specification plus the rows of every
  bi view it reads, as JSON; the browser renders charts from it.
* ``/wall/`` — full-screen kiosk page that rotates through the four dashboards;
  open to staff and to the ``wall_display`` role, which can do nothing else.

Nothing here queries the operational tables directly: all numbers come from the
materialised ``bi`` views refreshed every five minutes, so the wall, the desk
page and Metabase always agree.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.utils import timezone

from apps.accounts import roles

from . import services
from .dashboards import DASHBOARDS, WALL_ORDER
from .models import DisplaySettings


def _is_kiosk(user) -> bool:
    """A kiosk account holds the wall_display role and nothing else."""
    return not user.is_superuser and user.role_names == {roles.WALL_DISPLAY}


def _can_view_dashboards(user) -> bool:
    return (user.is_staff_user or user.is_superuser or user.has_role(roles.BI_ANALYST)) and not _is_kiosk(user)


def _can_view_wall(user) -> bool:
    return _can_view_dashboards(user) or user.has_role(roles.WALL_DISPLAY)


def _json_safe(value):
    """Make bi rows JSON-serialisable (Decimal → float, dates → ISO strings)."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows(view: str) -> list[dict]:
    return [{k: _json_safe(v) for k, v in row.items()} for row in services.fetch(view)]


def dashboard_payload(slug: str, wall: bool = False) -> dict:
    """Specification + data for one dashboard; ``wall=True`` drops panels that are not wall-safe."""
    d = DASHBOARDS[slug]
    panels = [p for p in d.panels if p.wall_safe or not wall]
    views = sorted({k.view for k in d.kpis} | {p.view for p in panels})
    return {
        "slug": d.slug, "title": d.title, "question": d.question, "source_note": d.source_note,
        "kpis": [k.__dict__ for k in d.kpis],
        "panels": [p.__dict__ for p in panels],
        "data": {v: _rows(v) for v in views},
        "generated_at": timezone.now().isoformat(),
        "refreshed_at": next((r.get("refreshed_at") for r in _rows(d.kpis[0].view) if r.get("refreshed_at")), None) if d.kpis else None,
    }


@login_required
def index(request):
    """List of the dashboards with their question."""
    if not _can_view_dashboards(request.user):
        raise PermissionDenied
    return render(request, "reports/index.html", {"dashboards": [DASHBOARDS[s] for s in WALL_ORDER]})


@login_required
def dashboard(request, slug):
    """Desk view of one dashboard."""
    if not _can_view_dashboards(request.user):
        raise PermissionDenied
    if slug not in DASHBOARDS:
        raise Http404
    ctx = {"dash": DASHBOARDS[slug], "dashboards": [DASHBOARDS[s] for s in WALL_ORDER], "refresh_seconds": DisplaySettings.get().page_refresh_seconds}
    return render(request, "reports/dashboard.html", ctx)


@login_required
def dashboard_data(request, slug):
    """JSON for one dashboard (``?wall=1`` for the wall-safe subset)."""
    if slug not in DASHBOARDS:
        raise Http404
    wall = request.GET.get("wall") == "1"
    if not (_can_view_wall(request.user) if wall else _can_view_dashboards(request.user)):
        raise PermissionDenied
    services.refresh_if_stale(DisplaySettings.get().data_refresh_minutes)  # near-real-time without a worker
    payload = dashboard_payload(slug, wall=wall)
    last = services.last_refreshed_at()
    if last:
        payload["refreshed_at"] = last.isoformat()
    return JsonResponse(payload)


@login_required
def wall(request):
    """Full-screen rotating display (design doc 13 §6)."""
    if not _can_view_wall(request.user):
        raise PermissionDenied
    ds = DisplaySettings.get()
    order = ds.order
    return render(request, "reports/wall.html", {
        "order": order, "rotate_seconds": ds.rotate_seconds, "refresh_seconds": ds.page_refresh_seconds, "show_clock": ds.show_clock,
        "start": request.GET.get("d", order[0]), "theme": request.GET.get("theme", ds.wall_theme),
        "exit_url": "/" if _is_kiosk(request.user) else "/dashboards/", "titles": {s: DASHBOARDS[s].title for s in order},
    })
