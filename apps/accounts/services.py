"""Account-level services: data-subject export and retention sweep (ToR §I)."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.core import audit


def personal_data_export(user) -> dict:
    data = {
        "account": {
            "email": user.email, "full_name": user.full_name, "phone": user.phone, "organisation": user.organisation,
            "created_at": user.created_at, "email_verified_at": user.email_verified_at,
            "privacy_notice_accepted_at": user.privacy_notice_accepted_at,
        },
        "licence_applications": list(
            user.licence_applications.values("reference", "status", "submitted_at", "parish__name", "water_source", "daily_volume_requested_m3")
        ),
        "submissions": list(user.submissions.values("id", "category_version__category__code", "status", "created_at")),
        "notifications": list(user.notifications.values("created_at", "kind", "title")[:500]),
    }
    return data


def anonymise_user(user, reason="retention"):
    """Irreversibly remove personal identifiers while keeping licence history (which
    WRA must retain) linked to an anonymised account."""
    pk = user.pk
    user.full_name = f"Removed user {pk}"
    user.email = f"removed-{pk}@anonymised.invalid"
    user.phone = ""
    user.organisation = ""
    user.is_active = False
    user.anonymised_at = timezone.now()
    user.set_unusable_password()
    user.save()
    user.notifications.all().delete()
    user.api_keys.update(revoked_at=timezone.now())
    audit.log("dpa.anonymised", user, summary=reason)


def retention_candidates():
    """Inactive client accounts past the retention window with no live licence."""
    from django.contrib.auth import get_user_model

    months = settings.WATERSOURCE["RETENTION"]["INACTIVE_CLIENT_ACCOUNT_MONTHS"]
    cutoff = timezone.now() - timedelta(days=30 * months)
    User = get_user_model()
    qs = User.objects.filter(user_type="client", anonymised_at__isnull=True).filter(
        last_login__lt=cutoff
    ) | User.objects.filter(user_type="client", anonymised_at__isnull=True, last_login__isnull=True, created_at__lt=cutoff)
    return [u for u in qs.distinct() if not u.licence_applications.filter(licence__status="active").exists()]
