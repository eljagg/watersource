from celery import shared_task
from django.db import connection

BI_VIEWS = ["bi.licensing_monthly", "bi.abstraction_vs_granted", "bi.water_quality_by_parish", "bi.application_turnaround", "bi.well_inventory"]


@shared_task
def refresh_bi_views():
    """Nightly and after bulk approvals: refresh the dashboard views (design plan §7)."""
    with connection.cursor() as cur:
        for v in BI_VIEWS:
            cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {v}")
    return BI_VIEWS
