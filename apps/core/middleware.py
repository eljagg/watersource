"""Request-scoped context: request id for log correlation and the current user
for the audit columns on AuditedModel."""
import threading
import uuid

_state = threading.local()


def get_current_user():
    return getattr(_state, "user", None)


def get_current_request():
    return getattr(_state, "request", None)


class RequestIDMiddleware:
    header = "HTTP_X_REQUEST_ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.id = request.META.get(self.header) or str(uuid.uuid4())
        _state.request = request
        try:
            response = self.get_response(request)
        finally:
            _state.request = None
        response["X-Request-ID"] = request.id
        return response


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        _state.user = getattr(request, "user", None)
        try:
            return self.get_response(request)
        finally:
            _state.user = None
