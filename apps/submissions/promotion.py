"""
Promotion: on final approval, write accepted/flagged rows into the typed target
table with approval_state=APPROVED and the chosen classification, in the same
transaction as the workflow's final action. Corrections update the existing row
and write obs.RecordHistory. Over-abstraction alerts are raised here
(ToR G.2.v, item 6.vii) so they fire only for approved data.
"""
from __future__ import annotations

from decimal import Decimal

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import FieldType, TargetModel
from apps.catalog.services import _ref_lookup
from apps.core import audit
from apps.core.models import ApprovalState, DataSource, NotificationKind
from apps.core.notifications import notify_group
from apps.obs.models import RecordHistory

from .models import RecordStatus, SubmissionStatus

_REF_TYPES = {FieldType.WELL, FieldType.STATION, FieldType.LICENCE, FieldType.SPRING}


def _resolve(field, value):
    if value is None:
        return None
    if field.field_type in _REF_TYPES:
        return _ref_lookup(field.field_type, value)
    if field.field_type in (FieldType.DECIMAL,):
        return Decimal(str(value))
    if field.field_type in (FieldType.DATE, FieldType.DATETIME):
        from django.utils.dateparse import parse_date, parse_datetime

        return parse_datetime(value) if field.field_type == FieldType.DATETIME else parse_date(value)
    return value


def _target_values(version, payload: dict) -> tuple[dict, dict]:
    """Split payload into (mapped column values, unmapped extras)."""
    mapped, extra = {}, {}
    fields = {f.name: f for f in version.fields.all()}
    for name, raw in payload.items():
        f = fields.get(name)
        if f is None:
            continue
        value = _resolve(f, raw)
        if f.target_field:
            mapped[f.target_field] = value
        else:
            extra[name] = raw
    return mapped, extra


def _normalise_for_model(Model, mapped: dict) -> dict:
    """Text columns are NOT NULL with blank=True: store '' rather than None."""
    from django.db.models import CharField, TextField

    out = dict(mapped)
    for name, value in mapped.items():
        if value is None:
            field = next((f for f in Model._meta.get_fields() if f.name == name), None)
            if isinstance(field, (CharField, TextField)) and not field.null:
                out[name] = ""
    return out


def _snapshot(obj, keys) -> dict:
    out = {}
    for k in keys:
        v = getattr(obj, k, None)
        out[k] = v if isinstance(v, (str, int, float, bool)) or v is None else str(v)
    return out


def _abstraction_limit(values: dict):
    lic = values.get("licence")
    start, end, volume = values.get("period_start"), values.get("period_end"), values.get("abstraction_volume_m3")
    if lic is None or start is None or end is None or volume is None:
        return None, False, None
    days = max(Decimal((end - start).total_seconds()) / Decimal(86400), Decimal(1))
    granted = Decimal(lic.daily_volume_granted_m3)
    allowed = granted * days
    over = Decimal(volume) > allowed
    pct = ((Decimal(volume) / allowed - 1) * 100).quantize(Decimal("0.01")) if allowed else None
    return granted, over, pct if over else None


@transaction.atomic
def promote(submission, actor, classification: str):
    version = submission.category_version
    target_label = version.category.target_model
    Model = apps.get_model(*target_label.split("."))
    now = timezone.now()
    over_limit_rows = []
    promoted = 0
    for rec in submission.records.select_for_update().filter(status__in=[RecordStatus.ACCEPTED, RecordStatus.FLAGGED]):
        mapped, extra = _target_values(version, rec.payload)
        mapped = _normalise_for_model(Model, mapped)
        if target_label == TargetModel.GENERIC:
            obj = Model(category_version=version, payload=rec.payload)
            for k in ("well", "station", "licence"):
                if k in mapped:
                    setattr(obj, k, mapped[k])
        elif rec.target_object_id and submission.is_correction:
            obj = rec.target
            old = _snapshot(obj, mapped.keys())
            for k, v in mapped.items():
                setattr(obj, k, v)
            RecordHistory.objects.create(
                content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk), old_values=old,
                new_values=_snapshot(obj, mapped.keys()), reason=submission.correction_reason,
                corrected_by=submission.submitter, corrected_at=submission.created_at, approved_by=actor, approved_at=now,
                submission=submission,
            )
        else:
            obj = Model(**mapped)
            if hasattr(obj, "extra") and extra:
                obj.extra = extra
        if target_label == TargetModel.ABSTRACTION:
            granted, over, pct = _abstraction_limit(mapped)
            obj.daily_volume_granted_m3 = granted
            obj.over_limit = over
            obj.over_limit_pct = pct
            if over:
                over_limit_rows.append(obj)
        obj.approval_state = ApprovalState.APPROVED
        obj.classification = classification
        obj.source = DataSource.API if submission.channel == "api" else DataSource.SUBMISSION
        obj.save()
        rec.status = RecordStatus.PROMOTED
        rec.promoted_content_type = ContentType.objects.get_for_model(obj)
        rec.promoted_object_id = str(obj.pk)
        rec.save(update_fields=["status", "promoted_content_type", "promoted_object_id"])
        promoted += 1
    submission.status = SubmissionStatus.APPROVED
    submission.classification = classification
    submission.save(update_fields=["status", "classification", "updated_at"])
    audit.log("submission.promoted", submission, summary=f"{promoted} rows → {target_label} as {classification}", actor=actor)
    if over_limit_rows:
        def _alert():
            for row in over_limit_rows:
                notify_group(
                    "reviewer", f"Abstraction above licensed volume — {row.licence.number}",
                    f"{row.abstraction_volume_m3} m³ recorded for {row.period_start:%d %b %Y}–{row.period_end:%d %b %Y}; "
                    f"licensed {row.daily_volume_granted_m3} m³/day. Licence expires {row.licence.expires_on:%d %b %Y}.",
                    kind=NotificationKind.OVER_ABSTRACTION, link=row.licence.get_absolute_url(), target=row.licence,
                )

        transaction.on_commit(_alert)
    return promoted
