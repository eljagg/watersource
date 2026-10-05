"""Data ownership by WRA unit (stakeholder model, package 1 — design doc 17).

The WRA Stakeholder–System Relationship Model gives each operating branch a
set of data it *owns*: it approves that data in the workflow and answers for
its quality; other branches read it (the dashed arrows). Three things carry
ownership:

* ``WorkflowStage.owning_unit`` — set on the licensing stages (Permits &
  Licences Unit, with the technical assessment owned by Resource Monitoring);
* ``DataCategory.owning_unit`` — set per submission category, because the
  data-submission workflow is shared by all categories;
* ``FAMILIES`` below — the reference and observation tables, by model label.

Both database fields are editable in the admin console, so a Super User can
move ownership without a developer. :func:`owner_for_stage` resolves the unit
that may act on a workflow item; :func:`unit_may_act` applies the rule.
"""
from __future__ import annotations

from django.apps import apps

#: model label → unit code (reference and observation families)
FAMILIES = {
    "ref.Well": "RMU", "ref.StreamflowStation": "RMU", "ref.Spring": "RMU", "ref.Instrument": "RMU", "ref.InstrumentInstallation": "RMU",
    "obs.WellWaterLevel": "RMU", "obs.StationReading": "RMU", "obs.WaterQualitySample": "RMU", "obs.ApprovalPeriod": "RMU",
    "lic.LicenceApplication": "PLU", "lic.Licence": "PLU", "lic.TechnicalAssessment": "PLU", "lic.LicenceCondition": "PLU", "obs.AbstractionRecord": "PLU",
    "ref.Basin": "PIU", "ref.WMU": "PIU", "ref.Aquifer": "PIU", "ref.HydrostratUnit": "PIU", "obs.ModelRun": "PIU", "obs.ModelOutput": "PIU",
}

#: submission category target model → unit code (used when a category has no owner set)
CATEGORY_DEFAULTS = {"obs.AbstractionRecord": "PLU", "obs.ModelOutput": "PIU"}
CATEGORY_FALLBACK = "RMU"

#: licence-application stage code → unit code
STAGE_DEFAULTS = {"intake": "PLU", "hydrogeology": "RMU", "licensing_officer": "PLU", "director": "PLU"}


def unit_code_for_model(label: str) -> str | None:
    """Owning unit code for a model label such as ``"ref.Well"``, or ``None``."""
    return FAMILIES.get(label)


def owner_for_stage(instance):
    """The unit that may act on ``instance`` at its current stage: the stage's own unit, else the subject's, else ``None`` (no restriction)."""
    stage = instance.current_stage
    if stage is not None and stage.owning_unit_id:
        return stage.owning_unit
    subject = instance.subject
    owner = getattr(subject, "owning_unit", None)
    return owner


def unit_may_act(user, instance) -> tuple[bool, str]:
    """``(allowed, reason)`` — superusers always may; otherwise the user's unit must be the owner when one is set."""
    if user.is_superuser:
        return True, ""
    owner = owner_for_stage(instance)
    if owner is None or getattr(user, "unit_id", None) == owner.pk:
        return True, ""
    mine = user.unit.name if getattr(user, "unit", None) else "no unit"
    return False, f"Only the {owner.name} may act on this item at stage '{instance.current_stage.name}' (you are in {mine})."


def families_owned_by(unit_code: str) -> list[str]:
    """Plain names of the reference/observation families a unit owns, for the admin console."""
    names = []
    for label, code in FAMILIES.items():
        if code == unit_code:
            try:
                names.append(str(apps.get_model(label)._meta.verbose_name_plural).capitalize())
            except LookupError:
                names.append(label)
    return names
