from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


def home(request):
    return render(request, "core/home.html")


def healthz(request):
    """Liveness/readiness probe for nginx, Railway and Uptime Kuma."""
    status = {"db": "ok", "cache": "ok"}
    code = 200
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as exc:  # pragma: no cover
        status["db"] = f"error: {exc.__class__.__name__}"
        code = 503
    try:
        cache.set("healthz", "1", 5)
        assert cache.get("healthz") == "1"
    except Exception as exc:  # pragma: no cover
        status["cache"] = f"error: {exc.__class__.__name__}"
        code = 503
    return JsonResponse({"status": "ok" if code == 200 else "degraded", **status}, status=code)


@login_required
def notifications(request):
    qs = request.user.notifications.all()[:100]
    return render(request, "core/notifications.html", {"notifications": qs})


@login_required
@require_POST
def notification_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return redirect(n.link or "core:notifications")


def privacy(request):
    """Privacy notice (DPA 2020 s.22 fair-processing information). Final wording is
    agreed with WRA's Data Protection Officer in the Requirements Specification."""
    return render(request, "core/privacy.html")
