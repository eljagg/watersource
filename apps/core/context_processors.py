"""Template context: site branding, URL and unread notification count."""
from django.conf import settings

from .branding import SiteBranding


def site(request):
    """Add ``branding``, ``SITE_NAME``, ``SITE_URL`` and ``unread_notifications`` to every template."""
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(read_at__isnull=True).count()
    branding = SiteBranding.get()
    return {"branding": branding, "SITE_NAME": branding.page_title, "SITE_URL": settings.SITE_URL, "unread_notifications": unread}
