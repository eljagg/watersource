"""
One definition → form, CSV template, JSON Schema, validation.

validate_row() is the single validation path for the web form, CSV import and
API (ToR G.2.iii). It returns (cleaned, errors, flags):
  errors: dict field -> [messages]  (hard failures; the row is rejected)
  flags:  list of messages          (soft findings; the reviewer sees them)
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import forms
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .models import CategoryVersion, FieldType, RuleType, Severity

_REF_MODELS = {
    FieldType.WELL: ("ref", "Well", "name"),
    FieldType.STATION: ("ref", "StreamflowStation", "name"),
    FieldType.LICENCE: ("lic", "Licence", "number"),
    FieldType.SPRING: ("ref", "Spring", "name"),
}


def _ref_lookup(field_type: str, value: str):
    from django.apps import apps

    app, model, key = _REF_MODELS[field_type]
    Model = apps.get_model(app, model)
    qs = Model.objects.filter(**{f"{key}__iexact": str(value).strip()})
    obj = qs.first()
    if obj is None and hasattr(Model, "aliases"):
        obj = Model.objects.filter(aliases__contains=[str(value).strip()]).first()
    return obj


# ---------------------------------------------------------------------------
# JSON Schema (for the API and drf-spectacular)
# ---------------------------------------------------------------------------
_JSON_TYPES = {
    FieldType.INTEGER: {"type": "integer"},
    FieldType.DECIMAL: {"type": "number"},
    FieldType.TEXT: {"type": "string"},
    FieldType.DATE: {"type": "string", "format": "date"},
    FieldType.DATETIME: {"type": "string", "format": "date-time"},
    FieldType.BOOLEAN: {"type": "boolean"},
    FieldType.ENUM: {"type": "string"},
    FieldType.WELL: {"type": "string", "description": "Well name or alias"},
    FieldType.STATION: {"type": "string", "description": "Station name or alias"},
    FieldType.LICENCE: {"type": "string", "description": "Licence number"},
    FieldType.SPRING: {"type": "string", "description": "Spring name"},
}


def build_json_schema(version: CategoryVersion) -> dict:
    props, required = {}, []
    for f in version.fields.all():
        schema = dict(_JSON_TYPES[f.field_type])
        schema["title"] = f.label
        if f.help_text:
            schema["description"] = f.help_text
        if f.unit:
            schema["x-unit"] = f.unit
        if f.field_type == FieldType.ENUM:
            schema["enum"] = list(f.choices)
        if f.min_value is not None:
            schema["minimum"] = float(f.min_value)
        if f.max_value is not None:
            schema["maximum"] = float(f.max_value)
        if f.regex:
            schema["pattern"] = f.regex
        props[f.name] = schema
        if f.required:
            required.append(f.name)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"urn:watersource:category:{version.category.code}:v{version.version}",
        "title": f"{version.category.name} (v{version.version})",
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# CSV template
# ---------------------------------------------------------------------------
def csv_template(version: CategoryVersion) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    fields = list(version.fields.all())
    w.writerow([f.name for f in fields])
    w.writerow([_example_for(f) for f in fields])
    return buf.getvalue()


def _example_for(f) -> str:
    return {
        FieldType.INTEGER: "1", FieldType.DECIMAL: "0.0", FieldType.TEXT: "text", FieldType.DATE: "2026-01-31",
        FieldType.DATETIME: "2026-01-31T08:00:00", FieldType.BOOLEAN: "yes", FieldType.ENUM: (f.choices or [""])[0],
        FieldType.WELL: "Well name", FieldType.STATION: "Station name", FieldType.LICENCE: "WRA-L-2026-000001", FieldType.SPRING: "Spring name",
    }[f.field_type]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
_TRUE = {"1", "true", "yes", "y", "t"}
_FALSE = {"0", "false", "no", "n", "f", ""}


def _coerce(f, raw):
    """Return (value, error). Accepts strings from CSV/forms and native JSON types."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None
    t = f.field_type
    try:
        if t == FieldType.INTEGER:
            return int(Decimal(str(raw))), None
        if t == FieldType.DECIMAL:
            return Decimal(str(raw)), None
        if t == FieldType.BOOLEAN:
            if isinstance(raw, bool):
                return raw, None
            s = str(raw).strip().lower()
            if s in _TRUE:
                return True, None
            if s in _FALSE:
                return False, None
            return None, "Enter yes or no."
        if t == FieldType.DATE:
            if isinstance(raw, date) and not isinstance(raw, datetime):
                return raw, None
            v = parse_date(str(raw).strip())
            return (v, None) if v else (None, "Use the date format YYYY-MM-DD.")
        if t == FieldType.DATETIME:
            if isinstance(raw, datetime):
                v = raw
            else:
                v = parse_datetime(str(raw).strip())
                if v is None:
                    d = parse_date(str(raw).strip())
                    v = datetime.combine(d, datetime.min.time()) if d else None
            if v is None:
                return None, "Use the format YYYY-MM-DDTHH:MM:SS."
            if timezone.is_naive(v):
                v = timezone.make_aware(v)
            return v, None
        if t == FieldType.ENUM:
            s = str(raw).strip()
            if s not in (f.choices or []):
                return None, f"Must be one of: {', '.join(f.choices)}."
            return s, None
        if t in _REF_MODELS:
            obj = _ref_lookup(t, raw)
            if obj is None:
                return None, f"Unknown {f.get_field_type_display().lower()} '{raw}'."
            return obj, None
        return str(raw).strip(), None
    except (InvalidOperation, ValueError):
        return None, "Not a valid number."


def validate_row(version: CategoryVersion, row: dict, *, batch_seen: set | None = None) -> tuple[dict, dict, list]:
    fields = list(version.fields.all())
    cleaned, errors, flags = {}, {}, []
    known = {f.name for f in fields}
    for key in row:
        if key not in known:
            errors.setdefault(key, []).append("Unexpected column.")
    for f in fields:
        value, err = _coerce(f, row.get(f.name))
        if err:
            errors.setdefault(f.name, []).append(err)
            continue
        if value is None:
            if f.required:
                errors.setdefault(f.name, []).append("This field is required.")
            cleaned[f.name] = None
            continue
        if f.field_type in (FieldType.INTEGER, FieldType.DECIMAL):
            if f.min_value is not None and value < f.min_value:
                errors.setdefault(f.name, []).append(f"Must be at least {f.min_value}.")
            if f.max_value is not None and value > f.max_value:
                errors.setdefault(f.name, []).append(f"Must be at most {f.max_value}.")
            if f.soft_min is not None and value < f.soft_min:
                flags.append(f"{f.label} ({value}) is below the expected range ({f.soft_min}).")
            if f.soft_max is not None and value > f.soft_max:
                flags.append(f"{f.label} ({value}) is above the expected range ({f.soft_max}).")
        if f.field_type == FieldType.TEXT and f.regex and not re.fullmatch(f.regex, value):
            errors.setdefault(f.name, []).append("Does not match the required format.")
        cleaned[f.name] = value

    for rule in version.rules.all():
        msg = _apply_rule(rule, cleaned, batch_seen)
        if msg:
            if rule.severity == Severity.HARD:
                errors.setdefault("__all__", []).append(msg)
            else:
                flags.append(msg)
    return cleaned, errors, flags


def _apply_rule(rule, c: dict, batch_seen) -> str | None:
    p = rule.params
    m = rule.message
    t = rule.rule_type
    try:
        if t == RuleType.DATE_ORDER:
            a, b = c.get(p["a"]), c.get(p["b"])
            if a and b and a > b:
                return m or f"{p['a']} must not be after {p['b']}."
        elif t == RuleType.RANGE_PAIR:
            a, b = c.get(p["a"]), c.get(p["b"])
            if a is not None and b is not None and a > b:
                return m or f"{p['a']} must be less than or equal to {p['b']}."
        elif t == RuleType.SUM_OF_PARTS:
            parts = [c.get(k) for k in p["parts"]]
            total = c.get(p["total"])
            if total is not None and all(x is not None for x in parts):
                tol = Decimal(str(p.get("tolerance", "0.01")))
                if abs(sum(parts) - total) > tol:
                    return m or f"{', '.join(p['parts'])} do not add up to {p['total']}."
        elif t == RuleType.REQUIRED_IF:
            if c.get(p["when"]) not in (None, "", False) and c.get(p["field"]) in (None, ""):
                return m or f"{p['field']} is required when {p['when']} is given."
        elif t == RuleType.UNIQUE_IN_BATCH:
            if batch_seen is not None:
                key = tuple(str(c.get(k)) for k in p["fields"])
                if key in batch_seen:
                    return m or f"Duplicate row for {', '.join(p['fields'])}."
                batch_seen.add(key)
        elif t == RuleType.LICENCE_LIMIT:
            return licence_limit_check(c, p, m)
    except KeyError as exc:
        return f"Rule misconfigured: missing parameter {exc}."
    return None


def licence_limit_check(c: dict, p: dict, m: str = "") -> str | None:
    """Compare submitted volume with the licence's daily grant over the period
    (ToR G.2.v). Soft by default: the row is flagged, the reviewer sees it, and the
    promotion step raises the over-abstraction alert."""
    licence = c.get(p.get("licence", "licence"))
    volume = c.get(p.get("volume", "abstraction_volume_m3"))
    start, end = c.get(p.get("start", "period_start")), c.get(p.get("end", "period_end"))
    if licence is None or volume is None or start is None or end is None:
        return None
    granted = getattr(licence, "daily_volume_granted_m3", None)
    if granted is None:
        return None
    days = max(Decimal((end - start).total_seconds()) / Decimal(86400), Decimal(1))
    allowed = Decimal(granted) * days
    if Decimal(volume) > allowed:
        pct = (Decimal(volume) / allowed - 1) * 100
        return m or f"Volume {volume} m³ exceeds the licensed {allowed:.0f} m³ for the period by {pct:.1f}%."
    return None


# ---------------------------------------------------------------------------
# Dynamic Django form
# ---------------------------------------------------------------------------
def form_class_for(version: CategoryVersion):
    attrs = {}
    for f in version.fields.all():
        common = dict(label=f.label + (f" ({f.unit})" if f.unit else ""), required=f.required, help_text=f.help_text)
        if f.field_type == FieldType.INTEGER:
            fld = forms.IntegerField(**common)
        elif f.field_type == FieldType.DECIMAL:
            fld = forms.DecimalField(**common)
        elif f.field_type == FieldType.DATE:
            fld = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}), **common)
        elif f.field_type == FieldType.DATETIME:
            fld = forms.DateTimeField(widget=forms.DateTimeInput(attrs={"type": "datetime-local"}), **common)
        elif f.field_type == FieldType.BOOLEAN:
            fld = forms.BooleanField(**{**common, "required": False})
        elif f.field_type == FieldType.ENUM:
            fld = forms.ChoiceField(choices=[(c, c) for c in f.choices], **common)
        else:
            fld = forms.CharField(**common)
        attrs[f.name] = fld

    def clean(self):
        cleaned, errors, flags = validate_row(version, {k: v for k, v in self.cleaned_data.items()})
        for field, msgs in errors.items():
            for msg in msgs:
                self.add_error(None if field == "__all__" or field not in self.fields else field, msg)
        self.flags = flags
        self.validated_row = cleaned
        return self.cleaned_data

    attrs["clean"] = clean
    return type(f"{version.category.code.title().replace('-', '')}V{version.version}Form", (forms.Form,), attrs)


def parse_csv(fileobj, version: CategoryVersion) -> list[dict]:
    text = fileobj.read()
    if isinstance(text, bytes):
        text = text.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    expected = [f.name for f in version.fields.all()]
    missing = [c for c in expected if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"CSV is missing columns: {', '.join(missing)}. Download the template for this category.")
    return [dict(r) for r in reader]
