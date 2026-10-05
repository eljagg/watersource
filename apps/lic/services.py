"""Licence application services: applicant party, submission to workflow, document attachment (ToR G.1)."""
from django.db import transaction
from django.utils import timezone

from apps.core import audit
from apps.core.uploads import clamav_scan, sha256_of
from apps.ref.models import Party, PartyKind
from apps.workflow import engine

from .models import ApplicationDocument, ApplicationStatus, LicenceApplication, ScanStatus


def party_for_user(user, name, address, email, phone) -> Party:
    """Return the user's ``Party``, creating or updating it from the form values."""
    if user.party_id:
        p = user.party
        changed = False
        for attr, val in (("name", name), ("address", address), ("email", email), ("phone", phone)):
            if val and getattr(p, attr) != val:
                setattr(p, attr, val)
                changed = True
        if changed:
            p.save()
        return p
    p = Party.objects.create(kind=PartyKind.APPLICANT, name=name, address=address, email=email, phone=phone)
    user.party = p
    user.save(update_fields=["party"])
    return p


@transaction.atomic
def submit_application(app: LicenceApplication, user) -> LicenceApplication:
    """Move a draft into review and start the licence workflow (requires at least one document)."""
    if app.status not in (ApplicationStatus.DRAFT,):
        raise ValueError("Only drafts can be submitted.")
    if not app.documents.exists():
        raise ValueError("Upload at least one supporting document before submitting.")
    app.status = ApplicationStatus.UNDER_REVIEW
    app.submitted_at = timezone.now()
    app.save(update_fields=["status", "submitted_at", "updated_at"])
    engine.start("licence_application", app, user, summary=f"{app.reference} · {app.applicant_name} · {app.parish.name}")
    audit.log("licence.application_submitted", app, actor=user)
    return app


def attach_document(app: LicenceApplication, form, user) -> ApplicationDocument:
    """Validate, scan, store and archive an uploaded document; raises ``ValueError`` if infected."""
    f = form.cleaned_data["file"]
    doc = form.save(commit=False)
    doc.application = app
    doc.original_name = f.name[:255]
    doc.content_type = getattr(form, "detected_type", "") or ""
    doc.size = f.size
    doc.sha256 = sha256_of(f)
    result = clamav_scan(f)
    doc.scan_status = ScanStatus.CLEAN if result == "clean" else ScanStatus.SKIPPED if result == "skipped" else ScanStatus.INFECTED
    doc.save()
    audit.log("licence.document_uploaded", doc, summary=doc.original_name, actor=user, scan=result)
    if doc.scan_status == ScanStatus.INFECTED:
        doc.file.delete(save=False)
        raise ValueError("The file failed the malware scan and was not stored.")
    from apps.integrations.tasks import push_document_to_dspace

    transaction.on_commit(lambda: push_document_to_dspace.delay(doc.pk))
    return doc


# ---------------------------------------------------------------------------
# WMU balance sheet (design doc 14 §4) — the numbers the technical assessment is made against
# ---------------------------------------------------------------------------
def wmu_balance(wmu) -> dict:
    """Safe yield, licensed allocation, reported abstraction and pending requests for one WMU (m³/day)."""
    from datetime import timedelta
    from decimal import Decimal

    from django.db.models import F, Q, Sum
    from django.utils import timezone

    from apps.obs.models import AbstractionRecord

    from .models import ApplicationStatus, Licence, LicenceStatus

    today = timezone.localdate()
    in_wmu = Q(wmu=wmu) | Q(wmu__isnull=True, well__wmu=wmu)
    allocated = Licence.objects.filter(in_wmu, status=LicenceStatus.ACTIVE, expires_on__gte=today).aggregate(v=Sum("daily_volume_granted_m3"))["v"] or Decimal(0)
    pending = LicenceApplication.objects.filter(in_wmu, status__in=[ApplicationStatus.SUBMITTED, ApplicationStatus.UNDER_REVIEW, ApplicationStatus.INFO_REQUESTED]) \
        .aggregate(v=Sum("daily_volume_requested_m3"))["v"] or Decimal(0)
    since = timezone.now() - timedelta(days=365)
    recs = AbstractionRecord.objects.filter(approval_state="approved", period_start__gte=since).filter(Q(licence__wmu=wmu) | Q(licence__wmu__isnull=True, well__wmu=wmu))
    total = recs.aggregate(v=Sum("abstraction_volume_m3"))["v"] or Decimal(0)
    days = recs.aggregate(d=Sum(F("period_end") - F("period_start")))["d"]
    day_count = Decimal(days.total_seconds() / 86400) if days else Decimal(0)
    reported = (total / day_count) if day_count else None
    safe = wmu.safe_yield_m3_d
    return {
        "wmu": wmu, "safe_yield": safe, "allocated": allocated, "pending": pending, "reported_avg": reported,
        "licences": Licence.objects.filter(in_wmu, status=LicenceStatus.ACTIVE).count(),
        "headroom": (safe - allocated) if safe is not None else None,
        "utilisation_pct": round(float(allocated / safe * 100), 1) if safe else None,
        "utilisation_with_pending_pct": round(float((allocated + pending) / safe * 100), 1) if safe else None,
    }
