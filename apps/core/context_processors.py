"""Template context: site name, URL and unread notification count."""
from django.conf import settings


def site(request):
    """Add ``SITE_NAME``, ``SITE_URL`` and ``unread_notifications`` to every template."""
    unread = 0
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        unread = user.notifications.filter(read_at__isnull=True).count()
    return {"SITE_NAME": "WaterSource Jamaica", "SITE_URL": settings.SITE_URL, "unread_notifications": unread}
