"""Create an in-app notification and queue the matching email (ToR H.xi)."""
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from .models import Notification, NotificationKind


def notify(user, title: str, body: str = "", *, kind=NotificationKind.SYSTEM, link: str = "", target=None) -> Notification:
    n = Notification(user=user, title=title, body=body, kind=kind, link=link)
    if target is not None:
        n.content_type = ContentType.objects.get_for_model(target)
        n.object_id = str(target.pk)
    n.save()
    from .tasks import send_notification_email

    transaction.on_commit(lambda: send_notification_email.delay(n.pk))
    return n


def notify_group(group_name: str, title: str, body: str = "", **kwargs):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    users = User.objects.filter(groups__name=group_name, is_active=True).distinct()
    return [notify(u, title, body, **kwargs) for u in users]
