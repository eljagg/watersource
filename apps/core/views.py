"""Public pages and the notification centre."""
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Notification


def home(request):
    """Landing page."""
    return render(request, "core/home.html")


def healthz(request):
    """Liveness/readiness probe for nginx, Railway and Uptime Kuma.

    Reports the database connection, whether every migration has been applied
    (``schema``) and the cache. A container serving an unmigrated database
    answers 503 so the platform never routes traffic to it.
    """
    status = {"db": "ok", "schema": "ok", "cache": "ok"}
    code = 200
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        from django.db.migrations.executor import MigrationExecutor

        pending = MigrationExecutor(connection).migration_plan(MigrationExecutor(connection).loader.graph.leaf_nodes())
        if pending:
            status["schema"] = f"pending: {len(pending)} migrations"
            code = 503
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
    """The user's notifications, newest first."""
    qs = request.user.notifications.all()[:100]
    return render(request, "core/notifications.html", {"notifications": qs})


@login_required
@require_POST
def notification_read(request, pk):
    """Mark one notification read and follow its link."""
    n = get_object_or_404(Notification, pk=pk, user=request.user)
    if n.read_at is None:
        n.read_at = timezone.now()
        n.save(update_fields=["read_at"])
    return redirect(n.link or "core:notifications")


def privacy(request):
    """Privacy notice (DPA 2020).

    The text is a placeholder until WRA's Data Protection Officer supplies the
    approved notice in the Requirements Specification.
    """
    return render(request, "core/privacy.html")
