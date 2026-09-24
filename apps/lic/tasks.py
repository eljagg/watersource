from datetime import date, timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.core.models import NotificationKind
from apps.core.notifications import notify, notify_group

from .models import Licence, LicenceStatus


@shared_task
def raise_expiry_alerts():
    """Item 14.xvii–xviii: alert applicant and staff ahead of expiry and on expiry."""
    today = date.today()
    warned = expired = 0
    for days in settings.WATERSOURCE["LICENCE_EXPIRY_WARNING_DAYS"]:
        target = today + timedelta(days=days)
        qs = Licence.objects.filter(status=LicenceStatus.ACTIVE, expires_on__lte=target, expires_on__gt=today).exclude(expiry_alerts_sent__contains=[days])
        for lic in qs:
            _alert(lic, f"Licence {lic.number} expires on {lic.expires_on:%d %b %Y}",
                   f"The licence for {lic.source_name} ({lic.parish.name}) expires in {lic.days_to_expiry} days. Apply for renewal before then.",
                   NotificationKind.LICENCE_EXPIRY)
            lic.expiry_alerts_sent = sorted(set(lic.expiry_alerts_sent) | {days})
            lic.save(update_fields=["expiry_alerts_sent", "updated_at"])
            warned += 1
    for lic in Licence.objects.filter(status=LicenceStatus.ACTIVE, expires_on__lt=today, expired_alert_sent_at__isnull=True):
        lic.status = LicenceStatus.EXPIRED
        lic.expired_alert_sent_at = timezone.now()
        lic.save(update_fields=["status", "expired_alert_sent_at", "updated_at"])
        _alert(lic, f"Licence {lic.number} has expired", f"The licence for {lic.source_name} expired on {lic.expires_on:%d %b %Y}.", NotificationKind.LICENCE_EXPIRED)
        expired += 1
    return {"warned": warned, "expired": expired}


def _alert(lic, title, body, kind):
    for user in lic.licensee.accounts.filter(is_active=True):
        notify(user, title, body, kind=kind, link=lic.get_absolute_url(), target=lic)
    notify_group("reviewer", title, body, kind=kind, link=lic.get_absolute_url(), target=lic)
