import logging

from celery import shared_task
from django.utils import timezone

from .models import IntegrationRun, IntegrationSystem

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=10, default_retry_delay=600)
def push_document_to_dspace(self, document_id: int):
    """Archive an application document in DSpace; a DSpace outage never blocks the applicant."""
    from apps.lic.models import ApplicationDocument

    from .dspace import DSpaceError, archive_application_document

    doc = ApplicationDocument.objects.select_related("application").get(pk=document_id)
    run = IntegrationRun.objects.create(system=IntegrationSystem.DSPACE, detail={"document": document_id})
    try:
        handle = archive_application_document(doc)
        doc.dspace_handle = handle
        doc.dspace_error = ""
        doc.save(update_fields=["dspace_handle", "dspace_error", "updated_at"])
        run.finish("ok" if handle else "skipped", handle=handle)
    except (DSpaceError, OSError) as exc:
        doc.dspace_error = str(exc)[:255]
        doc.save(update_fields=["dspace_error", "updated_at"])
        run.finish("error", error=str(exc)[:500])
        raise self.retry(exc=exc) from exc


@shared_task
def sync_aquarius():
    from apps.ref.models import StreamflowStation

    from .aquarius import AquariusClient

    client = AquariusClient()
    run = IntegrationRun.objects.create(system=IntegrationSystem.AQUARIUS)
    if not client.enabled:
        run.finish("skipped")
        return "skipped"
    try:
        client.connect()
        read = written = 0
        for loc in client.locations():
            read += 1
            ident = loc.get("Identifier", "")
            st = StreamflowStation.objects.filter(aquarius_identifier=ident).first() or StreamflowStation.objects.filter(name__iexact=loc.get("Name", "")).first()
            if st and not st.aquarius_identifier:
                st.aquarius_identifier = ident
                st.save(update_fields=["aquarius_identifier", "updated_at"])
                written += 1
        run.records_read, run.records_written = read, written
        run.finish("ok")
    except Exception as exc:  # pragma: no cover - network
        run.finish("error", error=str(exc)[:500])
        raise
    return {"read": read, "written": written}


@shared_task
def sync_hga():
    run = IntegrationRun.objects.create(system=IntegrationSystem.HGA)
    from django.conf import settings

    if not settings.HGA_ODBC_DSN:
        run.finish("skipped")
        return "skipped"
    from .hga import connect, fetch_wells

    try:
        conn = connect()
        n = sum(1 for _ in fetch_wells(conn))
        run.records_read = n
        run.finish("ok")
    except Exception as exc:  # pragma: no cover
        run.finish("error", error=str(exc)[:500])
        raise
    return n


@shared_task
def export_arcgis():
    from .exports import export_public_geojson

    run = IntegrationRun.objects.create(system=IntegrationSystem.ARCGIS)
    files = export_public_geojson()
    run.output_path = ";".join(files)
    run.finish("ok", files=files)
    return files


@shared_task
def export_finance(period_start=None, period_end=None):
    from datetime import date

    from .exports import export_finance_csv

    today = timezone.now().date()
    start = date.fromisoformat(period_start) if period_start else today.replace(day=1)
    end = date.fromisoformat(period_end) if period_end else today
    run = IntegrationRun.objects.create(system=IntegrationSystem.FINANCE)
    path = export_finance_csv(start, end)
    run.output_path = path
    run.finish("ok")
    return path
