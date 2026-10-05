"""Statistical anomaly flags for reviewers (AI feature 1, design doc 12 §AI; tracker "anomaly flags").

Runs once per submission after validation. It never rejects a row — it adds
plain-English findings to ``SubmissionRecord.flags`` and moves the row to
*Flagged for review* so the reviewer's eye goes to it first. Everything is
computed from WRA's own approved record with robust statistics (median and
median absolute deviation), so one bad historical value does not poison the
test. No external service, no model weights, deterministic and explainable:
every message says what was compared with what.

Checks (per target table, where the columns exist):

* **Out of character for this site** — value more than 3.5 robust standard
  deviations from the site's approved median (needs ≥ 8 approved readings).
* **Big jump** — change from the latest approved reading larger than 3.5 robust
  deviations of the site's historical step size.
* **Already on record** — an approved row with the same site and timestamp exists
  (a re-submission, or a correction that should have used the correction path).
* **In the future** — timestamp after now.
* **Flat line** — the same value repeated 6+ times in a row for one site within
  the batch (stuck sensor / copy-paste).
* **Abstraction out of pattern** — daily-equivalent volume more than 3× or less
  than ⅓ of the licence's approved median.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from statistics import median

from django.apps import apps
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog.models import FieldType, TargetModel
from apps.catalog.services import _ref_lookup

from .models import RecordStatus

MIN_HISTORY = 8
Z_LIMIT = 3.5
FLAT_RUN = 6
HISTORY_ROWS = 400

#: target model → (site payload fields, time field, value fields)
PROFILES = {
    TargetModel.WELL_WATER_LEVEL: (("well",), "measured_at", ("water_level_m",)),
    TargetModel.STATION_READING: (("station",), "read_at", ("discharge_m3_s", "recorder_reading_m", "observer_reading_m")),
    TargetModel.WATER_QUALITY: (("well", "station", "spring"), "sampled_at",
                                ("ph", "temperature_c", "specific_conductivity_us_cm", "chloride_mg_l", "nitrate_mg_l", "total_dissolved_solids_mg_l", "hardness_mg_l")),
    TargetModel.ABSTRACTION: (("licence",), "period_start", ("abstraction_volume_m3",)),
}


def _dec(v):
    try:
        return Decimal(str(v)) if v not in (None, "") else None
    except InvalidOperation:
        return None


def _dt(v):
    if isinstance(v, datetime):
        return v
    d = parse_datetime(str(v)) if v else None
    if d is not None and timezone.is_naive(d):
        d = timezone.make_aware(d)
    return d


def robust_z(x: Decimal, history: list[Decimal]) -> float | None:
    """Robust z-score of ``x`` against ``history`` (0.6745·(x−median)/MAD); ``None`` when not computable."""
    if len(history) < MIN_HISTORY:
        return None
    med = median(history)
    mad = median([abs(h - med) for h in history])
    if mad == 0:
        return None
    return float(Decimal("0.6745") * (x - med) / mad)


class _History:
    """Lazy per-site cache of approved values from the target table."""

    def __init__(self, Model, time_field):
        self.Model, self.time_field = Model, time_field
        self._cache: dict = {}

    def rows(self, site_field: str, site) -> list[dict]:
        key = (site_field, site.pk)
        if key not in self._cache:
            qs = self.Model.objects.filter(**{site_field: site, "approval_state": "approved"}).order_by(f"-{self.time_field}")
            self._cache[key] = list(qs.values()[:HISTORY_ROWS])
        return self._cache[key]


def _site_for(payload, site_fields, version_fields):
    for sf in site_fields:
        raw = payload.get(sf)
        f = version_fields.get(sf)
        if raw and f is not None and f.field_type in (FieldType.WELL, FieldType.STATION, FieldType.SPRING, FieldType.LICENCE):
            obj = _ref_lookup(f.field_type, raw)
            if obj is not None:
                return sf, obj
    return None, None


def _label(version_fields, name):
    f = version_fields.get(name)
    return f.label if f is not None else name


def flag_anomalies(submission) -> int:
    """Add anomaly findings to the submission's records; returns the number of rows newly flagged."""
    version = submission.category_version
    target = version.category.target_model
    profile = PROFILES.get(target)
    vf = {f.name: f for f in version.fields.all()}
    Model = apps.get_model(*target.split(".")) if profile else None
    records = list(submission.records.exclude(status=RecordStatus.REJECTED).order_by("row_no"))
    now = timezone.now()
    newly = 0
    history = _History(Model, profile[1]) if profile else None
    runs: dict = defaultdict(list)  # (site, value field) → consecutive equal values

    for rec in records:
        findings: list[str] = []
        p = rec.payload
        time_name = profile[1] if profile else next((n for n, f in vf.items() if f.field_type == FieldType.DATETIME), None)
        when = _dt(p.get(time_name)) if time_name else None
        if when is not None and when > now:
            findings.append(f"{_label(vf, time_name)} is in the future ({when:%d %b %Y %H:%M}).")

        if profile:
            site_fields, time_field, value_fields = profile
            sf, site = _site_for(p, site_fields, vf)
            if site is not None:
                hist = history.rows(sf, site)
                # already on record
                if when is not None and any(h.get(time_field) is not None and abs((h[time_field] - when).total_seconds()) < 60 for h in hist):
                    findings.append(f"An approved record for {site} at {when:%d %b %Y %H:%M} already exists — is this a duplicate or a correction?")
                for vname in value_fields:
                    x = _dec(p.get(vname))
                    if x is None:
                        continue
                    if target == TargetModel.ABSTRACTION:
                        findings += _abstraction_findings(p, x, hist, vf)
                        continue
                    series = [Decimal(str(h[vname])) for h in hist if h.get(vname) is not None]
                    z = robust_z(x, series)
                    out_of_character = z is not None and abs(z) > Z_LIMIT
                    if out_of_character:
                        med = median(series)
                        findings.append(f"{_label(vf, vname)} {x} is out of character for {site}: {abs(z):.1f} robust deviations from the approved median {med} (n={len(series)}).")
                    # big jump from the latest approved reading (only worth saying when the value itself looks normal)
                    if not out_of_character and len(series) >= MIN_HISTORY:
                        steps = [abs(series[i] - series[i + 1]) for i in range(len(series) - 1)]
                        step = abs(x - series[0])
                        zs = robust_z(step, steps)
                        if zs is not None and zs > Z_LIMIT:
                            findings.append(f"{_label(vf, vname)} jumps {step} from the latest approved value {series[0]} — "
                                            "far larger than this site's usual change between readings.")
                    # flat line within the batch
                    key = (sf, site.pk, vname)
                    seq = runs[key]
                    if seq and seq[-1] == x:
                        seq.append(x)
                    else:
                        runs[key] = [x]
                    if len(runs[key]) == FLAT_RUN:
                        findings.append(f"{_label(vf, vname)} repeats the same value ({x}) {FLAT_RUN} times in a row for {site} — stuck instrument or copied cells?")

        if findings:
            rec.flags = list(rec.flags) + [f"Anomaly: {m}" for m in findings]
            if rec.status == RecordStatus.ACCEPTED:
                rec.status = RecordStatus.FLAGGED
                newly += 1
            rec.save(update_fields=["flags", "status"])

    if newly:
        submission.accepted_count = submission.records.filter(status=RecordStatus.ACCEPTED).count()
        submission.flagged_count = submission.records.filter(status=RecordStatus.FLAGGED).count()
    return newly


def _abstraction_findings(p, volume: Decimal, hist: list[dict], vf) -> list[str]:
    """Daily-equivalent volume against the licence's approved pattern."""
    start, end = _dt(p.get("period_start")), _dt(p.get("period_end"))
    if start is None or end is None:
        return []
    days = max(Decimal((end - start).total_seconds()) / Decimal(86400), Decimal(1))
    per_day = volume / days
    past = []
    for h in hist:
        v, s, e = h.get("abstraction_volume_m3"), h.get("period_start"), h.get("period_end")
        if v is None or s is None or e is None:
            continue
        d = max(Decimal((e - s).total_seconds()) / Decimal(86400), Decimal(1))
        past.append(Decimal(str(v)) / d)
    if len(past) < 3:
        return []
    med = median(past)
    if med == 0:
        return []
    ratio = per_day / med
    if ratio > 3:
        return [f"Volume works out at {per_day:.0f} m³/day — {ratio:.1f}× this licence's usual {med:.0f} m³/day."]
    if ratio < Decimal("0.33"):
        pct = ratio * 100
        return [f"Volume works out at {per_day:.0f} m³/day — only {pct:.0f}% of this licence's usual {med:.0f} m³/day."]
    return []
