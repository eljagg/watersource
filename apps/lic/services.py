from django.db import transaction
from django.utils import timezone

from apps.core import audit
from apps.core.uploads import clamav_scan, sha256_of
from apps.ref.models import Party, PartyKind
from apps.workflow import engine

from .models import ApplicationDocument, ApplicationStatus, LicenceApplication, ScanStatus


def party_for_user(user, name, address, email, phone) -> Party:
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
