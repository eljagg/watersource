"""Create submissions from any channel and hand them to the workflow."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import CategoryVersion
from apps.catalog.services import parse_csv, validate_row
from apps.core import audit
from apps.core.uploads import sha256_of
from apps.workflow import engine

from .models import Channel, ImportRun, RecordStatus, Submission, SubmissionRecord, SubmissionStatus


def _serialisable(value):
    """Store references by natural key and Decimals as strings in JSONB."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    for attr in ("number", "name"):
        if hasattr(value, attr):
            return getattr(value, attr)
    return str(value)


def _store_rows(submission: Submission, version: CategoryVersion, rows: list[dict], targets: list | None = None):
    seen: set = set()
    accepted = flagged = rejected = 0
    records = []
    for i, row in enumerate(rows, start=1):
        cleaned, errors, flags = validate_row(version, row, batch_seen=seen)
        if errors:
            status = RecordStatus.REJECTED
            rejected += 1
        elif flags:
            status = RecordStatus.FLAGGED
            flagged += 1
        else:
            status = RecordStatus.ACCEPTED
            accepted += 1
        rec = SubmissionRecord(
            submission=submission, row_no=i, payload={k: _serialisable(v) for k, v in cleaned.items()} if not errors else dict(row),
            errors=errors, flags=flags, status=status,
        )
        if targets:
            t = targets[i - 1]
            rec.target_content_type = ContentType.objects.get_for_model(t)
            rec.target_object_id = str(t.pk)
        records.append(rec)
    SubmissionRecord.objects.bulk_create(records)
    submission.row_count = len(rows)
    submission.accepted_count, submission.flagged_count, submission.rejected_count = accepted, flagged, rejected
    return accepted, flagged, rejected


@transaction.atomic
def create_submission(version: CategoryVersion, rows: list[dict], user, *, channel=Channel.FORM, note="", fileobj=None,
                      idempotency_key="", is_correction=False, correction_reason="", targets=None) -> Submission:
    if version.status != "published":
        raise ValueError("This category version is not published.")
    if idempotency_key:
        existing = Submission.objects.filter(api_idempotency_key=idempotency_key, submitter=user).first()
        if existing:
            return existing
    sub = Submission(
        category_version=version, submitter=user, party=getattr(user, "party", None), channel=channel,
        submitter_note=note, api_idempotency_key=idempotency_key, is_correction=is_correction, correction_reason=correction_reason,
        status=SubmissionStatus.VALIDATING,
    )
    if fileobj is not None:
        sub.file = fileobj
        sub.original_filename = fileobj.name[:255]
    sub.save()
    run = ImportRun.objects.create(submission=sub, rows_in=len(rows), file_sha256=sha256_of(fileobj) if fileobj is not None else "")
    accepted, flagged, rejected = _store_rows(sub, version, rows, targets)
    run.rows_accepted, run.rows_flagged, run.rows_rejected = accepted, flagged, rejected
    run.finished_at = timezone.now()
    if rejected and channel != Channel.FORM and rejected == len(rows):
        sub.status = SubmissionStatus.FAILED_VALIDATION
        run.status = "failed"
    elif rejected:
        # partial: reviewer sees rejected rows but only accepted/flagged rows can be promoted
        sub.status = SubmissionStatus.UNDER_REVIEW
        run.status = "partial"
    else:
        sub.status = SubmissionStatus.UNDER_REVIEW
        run.status = "ok"
    sub.save()
    run.save()
    audit.log("submission.created", sub, summary=sub.summary, actor=user, channel=channel, accepted=accepted, flagged=flagged, rejected=rejected)
    if sub.status == SubmissionStatus.UNDER_REVIEW:
        wf_code = "correction" if is_correction else version.category.workflow.code
        engine.start(wf_code, sub, user, summary=("Correction · " if is_correction else "") + sub.summary)
    return sub


def create_from_csv(version: CategoryVersion, fileobj, user, note="") -> Submission:
    rows = parse_csv(fileobj, version)
    if not rows:
        raise ValueError("The CSV file has no data rows.")
    if len(rows) > 50000:
        raise ValueError("Split files larger than 50,000 rows.")
    fileobj.seek(0)
    return create_submission(version, rows, user, channel=Channel.CSV, note=note, fileobj=fileobj)


def create_correction(version: CategoryVersion, target, new_values: dict, user, reason: str) -> Submission:
    """A correction to an approved record re-enters the workflow (ToR H.xviii)."""
    if not reason.strip():
        raise ValueError("A reason for the correction is required.")
    return create_submission(version, [new_values], user, channel=Channel.FORM, is_correction=True,
                             correction_reason=reason, targets=[target])
