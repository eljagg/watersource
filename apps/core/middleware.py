"""Request-scoped context: request id for log correlation and the current user for the audit columns on AuditedModel."""
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
