"""Hydrologist QA services for observations (design doc 14 §3.2, ToR H.ix, H.xvii–xxi).

Two operations the technical roles need that the generic workflow does not
give them:

* :func:`approve_period` — approve every working/in-review row of one series at
  one site over a time window and record the period.
* :func:`regrade` — change grade/qualifiers on a row; when the row is already
  approved the change is written to ``RecordHistory`` so the approved record
  stays traceable.

Both run inside a transaction and write an audit entry.
"""
from __future__ import annotations

from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts import roles
from apps.core import audit
from apps.core.models import ApprovalState

from .models import AbstractionRecord, ApprovalPeriod, HistoryMethod, RecordHistory, SeriesKind, StationReading, WaterQualitySample, WellWaterLevel

#: Series → (model, site field, timestamp field)
SERIES = {
    SeriesKind.WELL_LEVEL: (WellWaterLevel, "well", "measured_at"),
    SeriesKind.STATION_STAGE: (StationReading, "station", "read_at"),
    SeriesKind.ABSTRACTION: (AbstractionRecord, None, "period_start"),
    SeriesKind.WATER_QUALITY: (WaterQualitySample, None, "sampled_at"),
}


def _check_can_approve(user) -> None:
    if user is None or not user.has_role(*roles.OBSERVATION_APPROVER_ROLES):
        raise PermissionDenied("Only hydrologists, hydrogeologists, approvers and administrators can approve observations.")


@transaction.atomic
def approve_period(series: str, site, starts_at: datetime, ends_at: datetime, user, remarks: str = "") -> ApprovalPeriod:
    """Approve all unapproved rows of ``series`` at ``site`` between the two timestamps.

    Args:
        series: a :class:`SeriesKind` value.
        site: a ``ref.Well`` or ``ref.StreamflowStation`` instance.
        starts_at: inclusive start of the period.
        ends_at: exclusive end of the period.
        user: the approving user; must hold an observation-approver role.
        remarks: free text stored on the period.

    Returns:
        The saved :class:`ApprovalPeriod` with ``rows_approved`` filled in.
    """
    _check_can_approve(user)
    if ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")
    model, site_field, ts_field = SERIES[series]
    site_kw = {}
    if site_field:
        site_kw[site_field] = site
    else:
        # abstraction and water quality can hang off a well or a station
        site_kw["well" if site.__class__.__name__ == "Well" else "station"] = site
    qs = model.objects.filter(**site_kw, **{f"{ts_field}__gte": starts_at, f"{ts_field}__lt": ends_at}).exclude(approval_state=ApprovalState.APPROVED)
    now = timezone.now()
    count = qs.update(approval_state=ApprovalState.APPROVED, updated_at=now, updated_by=user)
    period = ApprovalPeriod.objects.create(
        series=series, well=site if site.__class__.__name__ == "Well" else None,
        station=site if site.__class__.__name__ == "StreamflowStation" else None,
        starts_at=starts_at, ends_at=ends_at, approved_by=user, rows_approved=count, remarks=remarks,
    )
    audit.log("observation.period_approved", period, summary=f"{count} rows of {series} approved for {site}", actor=user)
    return period


@transaction.atomic
def regrade(obj, grade: str, qualifiers: list[str] | None, user, reason: str = "") -> None:
    """Set grade/qualifiers on one observation, keeping history if it was approved.

    Technicians may grade working rows; only observation approvers may touch an
    approved row, and that change is recorded in ``RecordHistory`` with method
    ``regrade`` (ToR H.xvii: corrections to approved data are traceable).
    """
    approved = obj.approval_state == ApprovalState.APPROVED
    if approved:
        _check_can_approve(user)
        if not reason:
            raise ValueError("A reason is required when re-grading an approved observation.")
        old = {"grade": obj.grade, "qualifiers": list(obj.qualifiers)}
    obj.set_grade(grade, qualifiers, user=user)
    obj.save(update_fields=["grade", "qualifiers", "graded_by", "graded_at", "updated_at", "updated_by"])
    if approved:
        RecordHistory.objects.create(
            content_type=ContentType.objects.get_for_model(obj), object_id=str(obj.pk), old_values=old,
            new_values={"grade": obj.grade, "qualifiers": list(obj.qualifiers)}, method=HistoryMethod.REGRADE, reason=reason,
            corrected_by=user, corrected_at=timezone.now(), approved_by=user, approved_at=timezone.now(),
        )
    audit.log("observation.regraded", obj, summary=f"grade={grade} qualifiers={obj.qualifiers}", actor=user)
