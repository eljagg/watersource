"""Session idle timeout, forced password change/rotation, and MFA enforcement
for privileged staff (ToR §9 'session timeout controls', H.iii, H.v)."""
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone

EXEMPT_PREFIXES = ("/accounts/", "/healthz", "/static/", "/admin/login", "/api/")


def _exempt(path):
    return path.startswith(EXEMPT_PREFIXES)


class SessionPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            last = request.session.get("last_activity")
            if last:
                idle = now - timezone.datetime.fromisoformat(last)
                if idle > timedelta(minutes=settings.SESSION_IDLE_MINUTES):
                    logout(request)
                    messages.info(request, "You were signed out after a period of inactivity.")
                    return redirect(settings.LOGIN_URL)
            request.session["last_activity"] = now.isoformat()
        return self.get_response(request)


class PasswordPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not _exempt(request.path):
            if user.must_change_password or user.password_expired:
                messages.warning(request, "Please choose a new password to continue.")
                return redirect(reverse("accounts:password_change"))
        return self.get_response(request)


class MFAEnforcementMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not _exempt(request.path):
            if user.mfa_required and not user.is_verified():
                return redirect(reverse("accounts:mfa_setup") if not _has_device(user) else reverse("accounts:mfa_verify"))
        return self.get_response(request)


def _has_device(user):
    from django_otp import user_has_device

    return user_has_device(user, confirmed=True)
