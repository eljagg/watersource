"""Seed the two initial data categories the ToR names: water abstraction (item 6)
and water quality (item 10). WRA refines field lists in the workshops; a new
version is published from the admin without code changes."""
from django.core.management.base import BaseCommand

from apps.catalog.models import (
    CategoryField,
    CategoryRule,
    CategoryVersion,
    DataCategory,
    FieldType,
    LinkKind,
    RuleType,
    Severity,
    TargetModel,
)
from apps.workflow.models import WorkflowDefinition

ABSTRACTION_FIELDS = [
    ("licence", "Licence number", FieldType.LICENCE, "", True, dict(target_field="licence")),
    ("well", "Well (if groundwater)", FieldType.WELL, "", False, dict(target_field="well")),
    ("source_type", "Abstraction source", FieldType.ENUM, "", True, dict(choices=["surface", "ground"], target_field="source_type")),
    ("period_start", "Period start", FieldType.DATETIME, "", True, dict(target_field="period_start")),
    ("period_end", "Period end", FieldType.DATETIME, "", True, dict(target_field="period_end")),
    ("abstraction_rate_m3_d", "Abstraction rate", FieldType.DECIMAL, "m³/day", False, dict(min_value=0, target_field="abstraction_rate_m3_d")),
    ("abstraction_volume_m3", "Volume abstracted", FieldType.DECIMAL, "m³", True, dict(min_value=0, target_field="abstraction_volume_m3")),
    ("meter_reading", "Meter reading", FieldType.DECIMAL, "m³", False, dict(min_value=0, target_field="meter_reading")),
    ("remarks", "Remarks", FieldType.TEXT, "", False, dict(target_field="remarks")),
]
ABSTRACTION_RULES = [
    (RuleType.DATE_ORDER, {"a": "period_start", "b": "period_end"}, Severity.HARD, "Period start must not be after period end."),
    (RuleType.LICENCE_LIMIT, {}, Severity.SOFT, ""),
    (RuleType.UNIQUE_IN_BATCH, {"fields": ["licence", "period_start"]}, Severity.HARD, ""),
]
WQ_FIELDS = [
    ("source_type", "Sample source", FieldType.ENUM, "", True, dict(choices=["well", "spring", "stream"], target_field="source_type")),
    ("well", "Well", FieldType.WELL, "", False, dict(target_field="well")),
    ("spring", "Spring", FieldType.SPRING, "", False, dict(target_field="spring")),
    ("station", "Stream station", FieldType.STATION, "", False, dict(target_field="station")),
    ("sample_ref", "Laboratory sample reference", FieldType.TEXT, "", False, dict(target_field="sample_ref")),
    ("sampled_at", "Date sampled", FieldType.DATETIME, "", True, dict(target_field="sampled_at")),
    ("analysed_at", "Date analysed", FieldType.DATETIME, "", False, dict(target_field="analysed_at")),
    ("sampled_by", "Sampled by", FieldType.TEXT, "", False, dict(target_field="sampled_by")),
    ("analysed_by", "Analysed by", FieldType.TEXT, "", False, dict(target_field="analysed_by")),
    ("sample_depth_m", "Sample depth", FieldType.DECIMAL, "m", False, dict(min_value=0, target_field="sample_depth_m")),
    ("specific_conductivity_us_cm", "Specific conductivity", FieldType.DECIMAL, "µS/cm", False, dict(min_value=0, soft_max=10000, target_field="specific_conductivity_us_cm")),
    ("temperature_c", "Temperature", FieldType.DECIMAL, "°C", False, dict(min_value=0, max_value=60, soft_min=15, soft_max=40, target_field="temperature_c")),
    ("ph", "pH", FieldType.DECIMAL, "", False, dict(min_value=0, max_value=14, soft_min=5.5, soft_max=9.5, target_field="ph")),
    ("colour", "Colour", FieldType.TEXT, "", False, dict(target_field="colour")),
    ("odour", "Odour", FieldType.TEXT, "", False, dict(target_field="odour")),
    ("turbidity_ntu", "Turbidity", FieldType.DECIMAL, "NTU", False, dict(min_value=0, target_field="turbidity_ntu")),
    ("percent_sodium", "Percentage sodium", FieldType.DECIMAL, "%", False, dict(min_value=0, max_value=100, target_field="percent_sodium")),
    ("sodium_adsorption_ratio", "Sodium adsorption ratio", FieldType.DECIMAL, "", False, dict(min_value=0, target_field="sodium_adsorption_ratio")),
    ("calcium_mg_l", "Calcium", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="calcium_mg_l")),
    ("magnesium_mg_l", "Magnesium", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="magnesium_mg_l")),
    ("potassium_mg_l", "Potassium", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="potassium_mg_l")),
    ("carbonate_mg_l", "Carbonate", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="carbonate_mg_l")),
    ("bicarbonate_mg_l", "Bicarbonate", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="bicarbonate_mg_l")),
    ("sulphate_mg_l", "Sulphates", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="sulphate_mg_l")),
    ("chloride_mg_l", "Chloride", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="chloride_mg_l")),
    ("nitrate_mg_l", "Nitrate", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, soft_max=50, target_field="nitrate_mg_l")),
    ("hardness_mg_l", "Hardness", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="hardness_mg_l")),
    ("alkalinity_mg_l", "Alkalinity", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="alkalinity_mg_l")),
    ("total_dissolved_solids_mg_l", "Total dissolved solids", FieldType.DECIMAL, "mg/L", False, dict(min_value=0, target_field="total_dissolved_solids_mg_l")),
]
WQ_RULES = [
    (RuleType.DATE_ORDER, {"a": "sampled_at", "b": "analysed_at"}, Severity.HARD, "Date analysed cannot be before date sampled."),
    (RuleType.REQUIRED_IF, {"when": "source_type", "field": "well"}, Severity.SOFT, "Well should be given for well samples."),
]


class Command(BaseCommand):
    help = "Create the initial data categories (idempotent)."

    def _seed(self, code, name, target, link, wf, fields, rules):
        cat, created = DataCategory.objects.get_or_create(
            code=code, defaults=dict(name=name, target_model=target, link_kind=link, workflow=wf)
        )
        if cat.versions.exists():
            self.stdout.write(f"exists  {code}")
            return
        v = CategoryVersion.objects.create(category=cat, version=1)
        for order, (fname, label, ftype, unit, req, extra) in enumerate(fields, start=1):
            CategoryField.objects.create(version=v, order=order, name=fname, label=label, field_type=ftype, unit=unit, required=req, **extra)
        for rtype, params, sev, msg in rules:
            CategoryRule.objects.create(version=v, rule_type=rtype, params=params, severity=sev, message=msg)
        v.publish()
        self.stdout.write(f"created {code} v1 ({len(fields)} fields)")

    def handle(self, *args, **options):
        wf = WorkflowDefinition.objects.get(code="data_submission_default")
        self._seed("water_abstraction", "Water abstraction (ToR item 6)", TargetModel.ABSTRACTION, LinkKind.LICENCE, wf, ABSTRACTION_FIELDS, ABSTRACTION_RULES)
        self._seed("water_quality", "Water quality (ToR item 10)", TargetModel.WATER_QUALITY, LinkKind.WELL, wf, WQ_FIELDS, WQ_RULES)
