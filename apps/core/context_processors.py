"""Template context: site branding, URL and unread notification count."""
from django.conf import settings

from .branding import SiteBranding


def breadcrumbs(request):
    """Breadcrumbs derived from the URL (``apps.core.breadcrumbs``) and the "← Back" target (v0.10.1).

    Back goes to the page the person came from when that page is inside
    WaterSource (same host, a different address); from a bookmark or an
    outside link it goes to Home.
    """
    from urllib.parse import urlsplit

    from .breadcrumbs import build

    back = "/"
    ref = urlsplit(request.META.get("HTTP_REFERER", ""))
    if ref.netloc == request.get_host() and ref.path and ref.path != request.path:
        back = ref.path + (f"?{ref.query}" if ref.query else "")
    return {"breadcrumbs": build(request.path), "back_url": back}


def site(request):
    """Add ``branding``, ``SITE_NAME``, ``SITE_URL`` and ``unread_notifications`` to every template."""
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(read_at__isnull=True).count()
    branding = SiteBranding.get()
    return {"branding": branding, "SITE_NAME": branding.page_title, "SITE_URL": settings.SITE_URL, "unread_notifications": unread}
