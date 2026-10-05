"""Celery tasks for account retention (ToR §I)."""
from celery import shared_task


@shared_task
def retention_sweep():
    """Nightly: anonymise client accounts past the retention window (ToR I.iii).

    Runs in 'report only' mode unless ``WATERSOURCE_RETENTION_ENFORCE=1`` — WRA's DPO
    confirms the periods in the Requirements Specification before enforcement.
    """
    import os

    from apps.core import audit

    from .services import anonymise_user, retention_candidates

    candidates = retention_candidates()
    enforce = os.environ.get("WATERSOURCE_RETENTION_ENFORCE") == "1"
    if enforce:
        for u in candidates:
            anonymise_user(u)
    audit.log("retention.sweep", None, summary=f"{len(candidates)} candidate(s), {'enforced' if enforce else 'report only'}")
    return {"candidates": len(candidates), "enforced": os.environ.get("WATERSOURCE_RETENTION_ENFORCE") == "1"}
