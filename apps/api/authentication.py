"""API-key authentication for system-to-system clients (telemetry, laboratories).
Header:  Authorization: Api-Key wsk_...   Keys are stored hashed; see accounts.APIKey."""
from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.accounts.models import APIKey


class APIKeyAuthentication(authentication.BaseAuthentication):
    keyword = "Api-Key"

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if not header.startswith(self.keyword + " "):
            return None
        raw = header[len(self.keyword) + 1 :].strip()
        if len(raw) < 12:
            raise exceptions.AuthenticationFailed("Invalid API key.")
        key = APIKey.objects.select_related("user").filter(prefix=raw[:12]).first()
        if key is None or not key.is_active or key.key_hash != APIKey.hash_key(raw):
            raise exceptions.AuthenticationFailed("Invalid or revoked API key.")
        if not key.user.is_active:
            raise exceptions.AuthenticationFailed("Account disabled.")
        APIKey.objects.filter(pk=key.pk).update(last_used_at=timezone.now())
        request.api_key = key
        return (key.user, key)

    def authenticate_header(self, request):
        return self.keyword


def has_scope(request, scope: str) -> bool:
    key = getattr(request, "api_key", None)
    if key is None:  # session-authenticated user: roles govern
        return True
    return scope in key.scopes or "*" in key.scopes


# drf-spectacular: document the Api-Key scheme in the OpenAPI file
try:
    from drf_spectacular.extensions import OpenApiAuthenticationExtension

    class APIKeyScheme(OpenApiAuthenticationExtension):
        target_class = "apps.api.authentication.APIKeyAuthentication"
        name = "ApiKeyAuth"

        def get_security_definition(self, auto_schema):
            return {"type": "apiKey", "in": "header", "name": "Authorization", "description": "Authorization: Api-Key wsk_…"}
except ImportError:  # pragma: no cover
    pass
