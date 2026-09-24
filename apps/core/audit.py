"""audit.log(...) is the one call every service uses to record an action.
It writes the AuditLog row inside the caller's transaction and emits a
structured log line for the central log."""
import logging

from django.contrib.contenttypes.models import ContentType

from .middleware import get_current_request, get_current_user
from .models import AuditLog

logger = logging.getLogger("watersource.audit")


def _client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log(action: str, target=None, summary: str = "", actor=None, **meta) -> AuditLog:
    request = get_current_request()
    actor = actor or get_current_user()
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None
    entry = AuditLog(
        actor=actor,
        action=action,
        summary=summary[:255],
        meta=meta,
        ip_address=_client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:255] if request else ""),
        request_id=getattr(request, "id", "") if request else "",
    )
    if target is not None:
        entry.content_type = ContentType.objects.get_for_model(target)
        entry.object_id = str(target.pk)
    entry.save()
    logger.info(
        "%s %s", action, summary,
        extra={
            "request_id": entry.request_id, "user_id": getattr(actor, "pk", None), "action": action,
            "object": f"{entry.content_type_id}:{entry.object_id}", "ip": entry.ip_address,
        },
    )
    return entry
