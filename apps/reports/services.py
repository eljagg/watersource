"""Read and refresh the ``bi`` schema (design doc 13).

Dashboards (Sprint 3) and Metabase both read the materialised views listed in
:data:`BI_VIEWS`; nothing else in the application queries ``bi.*`` directly.
Views are refreshed by the Celery beat job every five minutes and after the
migrate step on deploy (``manage.py refresh_bi_views``).
"""
from __future__ import annotations

from django.db import connection

#: Every materialised view, in dependency order. Keep in step with the reports migrations.
BI_VIEWS = [
    "bi.licensing_monthly",
    "bi.abstraction_vs_granted",
    "bi.water_quality_by_parish",
    "bi.application_turnaround",
    "bi.well_inventory",
    "bi.licensing_pipeline",
    "bi.applications_monthly",
    "bi.licence_expiry",
    "bi.licence_active_by_parish",
    "bi.licensing_kpis",
    # dashboards (migration 0003) — order matters: kpis views read the status/share views
    "bi.application_stage_counts",
    "bi.open_applications_by_parish",
    "bi.longest_waiting_applications",
    "bi.well_level_status",
    "bi.station_flow_status",
    "bi.groundwater_index_by_basin",
    "bi.station_flow_recent",
    "bi.abstraction_share_latest",
    "bi.wq_exceedances_90d",
    "bi.monitoring_kpis",
    "bi.submissions_monthly",
    "bi.review_backlog_age",
    "bi.observation_grades",
    "bi.validation_failures",
    "bi.submissions_kpis",
    "bi.licences_by_status",
    "bi.service_standard_monthly",
    "bi.expiries_next_12m",
    "bi.governance_kpis",
    "bi.executive_kpis",
]
#: Views the Licensing overview dashboard reads (design doc 13 §5.1).
LICENSING_DASHBOARD = ["bi.licensing_kpis", "bi.licensing_pipeline", "bi.applications_monthly", "bi.licence_expiry", "bi.licence_active_by_parish", "bi.licensing_monthly"]


def _valid(view: str) -> str:
    if view not in BI_VIEWS:
        raise ValueError(f"Unknown bi view {view!r}")
    return view


def refresh(view: str) -> None:
    """Refresh one materialised view.

    ``CONCURRENTLY`` keeps the view readable during refresh but cannot run
    inside a transaction, so inside ``atomic`` blocks (tests) a plain refresh is
    used instead.
    """
    _valid(view)
    concurrently = "" if connection.in_atomic_block else "CONCURRENTLY "
    with connection.cursor() as cur:
        cur.execute(f"REFRESH MATERIALIZED VIEW {concurrently}{view}")  # noqa: S608 — name validated against BI_VIEWS


def refresh_all() -> list[str]:
    """Refresh every view in :data:`BI_VIEWS`, in order, and stamp the time in the cache."""
    from django.core.cache import cache
    from django.utils import timezone

    for view in BI_VIEWS:
        refresh(view)
    cache.set("bi:refreshed_at", timezone.now().isoformat(), None)
    return list(BI_VIEWS)


def last_refreshed_at():
    """When the views were last refreshed (from cache; ``None`` if unknown)."""
    from django.core.cache import cache
    from django.utils.dateparse import parse_datetime

    raw = cache.get("bi:refreshed_at")
    return parse_datetime(raw) if raw else None


def refresh_if_stale(max_age_minutes: int) -> bool:
    """Refresh the views when they are older than ``max_age_minutes``; returns True if a refresh ran.

    This is what keeps dashboards near-real-time on a deployment without a
    Celery worker (Railway staging): opening a dashboard or the wall triggers
    the refresh, guarded by a 60-second cache lock so concurrent viewers do not
    stampede the database. With Celery beat present the scheduled task does
    the same check every minute and viewers rarely pay for it.
    """
    from datetime import timedelta

    from django.core.cache import cache
    from django.utils import timezone

    last = last_refreshed_at()
    if last and timezone.now() - last < timedelta(minutes=max_age_minutes):
        return False
    if not cache.add("bi:refresh_lock", "1", 60):
        return False
    try:
        refresh_all()
    finally:
        cache.delete("bi:refresh_lock")
    return True


def fetch(view: str, order_by: str | None = None, limit: int | None = None) -> list[dict]:
    """Return the rows of a bi view as dicts (column names as keys).

    Args:
        view: a name from :data:`BI_VIEWS`.
        order_by: optional column name (must exist in the view) to sort by.
        limit: optional maximum row count.
    """
    _valid(view)  # view names below are validated against BI_VIEWS, never user input
    sql = f"SELECT * FROM {view}"  # noqa: S608 # nosec B608
    params: list = []
    with connection.cursor() as cur:
        if order_by:
            cur.execute(f"SELECT * FROM {view} LIMIT 0")  # noqa: S608 # nosec B608
            columns = {c[0] for c in cur.description}
            if order_by.lstrip("-") not in columns:
                raise ValueError(f"{order_by!r} is not a column of {view}")
            sql += f" ORDER BY {order_by.lstrip('-')} {'DESC' if order_by.startswith('-') else 'ASC'}"
        if limit:
            sql += " LIMIT %s"
            params.append(int(limit))
        cur.execute(sql, params)
        names = [c[0] for c in cur.description]
        return [dict(zip(names, row, strict=True)) for row in cur.fetchall()]


def licensing_dashboard() -> dict[str, list[dict]]:
    """All rows the Licensing overview dashboard needs, keyed by short view name."""
    return {v.split(".")[1]: fetch(v) for v in LICENSING_DASHBOARD}


__all__ = ["BI_VIEWS", "LICENSING_DASHBOARD", "refresh", "refresh_all", "fetch", "licensing_dashboard"]
