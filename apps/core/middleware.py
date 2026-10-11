"""Request-scoped context: request id for log correlation and the current user for the audit columns on AuditedModel."""
import logging
import threading
import uuid

_state = threading.local()


def get_current_user():
    """The user of the request being handled on this thread, or ``None``."""
    return getattr(_state, "user", None)


def get_current_request():
    """The request being handled on this thread, or ``None``."""
    return getattr(_state, "request", None)


class RequestIDMiddleware:
    """Attach a UUID ``request.id`` and echo it in the ``X-Request-ID`` response header."""
    header = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Set the id, store the request in thread-local state, and clear it afterwards."""
        request.id = request.META.get(self.header) or str(uuid.uuid4())
        _state.request = request
        try:
            response = self.get_response(request)
        finally:
            _state.request = None
        response["X-Request-ID"] = request.id
        return response


class CurrentUserMiddleware:
    """Expose the authenticated user to model ``save()`` via thread-local state."""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Store the user for the duration of the request."""
        _state.user = getattr(request, "user", None)
        try:
            return self.get_response(request)
        finally:
            _state.user = None


class RecentViewMiddleware:
    """Remember the pages a signed-in person opens, for the "Last viewed" list on Home (v0.10.0).

    Only full-page ``GET`` requests that rendered HTML successfully count; the
    home page, sign-in and account pages, the admin console, the API and
    HTMX partial requests do not. Failures to record never break the page.
    """
    SKIP = ("/accounts/", "/admin/", "/api/", "/healthz", "/static/", "/media/", "/notifications/", "/privacy/", "/maps/layers/", "/maps/full/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Serve the page, then record it."""
        response = self.get_response(request)
        try:
            self._record(request, response)
        except Exception:  # pragma: no cover - never let bookkeeping break a page
            logging.getLogger(__name__).warning("recent view not recorded", exc_info=True)
        return response

    def _record(self, request, response):
        user = getattr(request, "user", None)
        if request.method != "GET" or response.status_code != 200 or not (user and user.is_authenticated):
            return
        if request.headers.get("HX-Request") or "text/html" not in response.get("Content-Type", ""):
            return
        path = request.path
        if path == "/" or path.startswith(self.SKIP):
            return
        from .breadcrumbs import build
        from .models import RecentView

        crumbs = build(path)
        if len(crumbs) < 2:
            return
        RecentView.remember(user, path, " › ".join(c["label"] for c in crumbs[1:]))
