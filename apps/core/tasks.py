import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=5, default_retry_delay=120)
def send_notification_email(self, notification_id: int):
    try:
        n = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        return
    if n.email_sent_at or not n.user.email:
        return
    body = n.body
    if n.link:
        body = f"{body}\n\nOpen: {settings.SITE_URL}{n.link}"
    try:
        send_mail(f"[WaterSource] {n.title}", body, settings.DEFAULT_FROM_EMAIL, [n.user.email], fail_silently=False)
        n.email_sent_at = timezone.now()
        n.email_error = ""
        n.save(update_fields=["email_sent_at", "email_error"])
    except Exception as exc:  # pragma: no cover - network
        n.email_error = str(exc)[:255]
        n.save(update_fields=["email_error"])
        logger.warning("email delivery failed for notification %s: %s", notification_id, exc)
        raise self.retry(exc=exc) from exc
