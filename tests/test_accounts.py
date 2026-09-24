import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.models import APIKey, EmailToken, User


@pytest.mark.django_db
def test_password_policy_rejects_weak_and_reused(client_user):
    with pytest.raises(ValidationError):
        validate_password("alllowercase12", client_user)  # only 2 classes
    with pytest.raises(ValidationError):
        validate_password("Short1!", client_user)
    validate_password("Another-Go0d-Passw0rd", client_user)


@pytest.mark.django_db
def test_registration_creates_unverified_client_and_token(client):
    resp = client.post(reverse("accounts:register"), {
        "full_name": "New Person", "email": "new@example.com", "phone": "", "organisation": "",
        "password1": "Str0ng-Passw0rd!x", "password2": "Str0ng-Passw0rd!x", "accept_privacy": "on",
    })
    assert resp.status_code == 200
    u = User.objects.get(email="new@example.com")
    assert u.is_client and u.email_verified_at is None and u.privacy_notice_accepted_at is not None
    token = EmailToken.objects.get(user=u)
    resp = client.get(reverse("accounts:verify", args=[token.token]))
    assert resp.status_code == 302
    u.refresh_from_db()
    assert u.email_verified_at is not None


@pytest.mark.django_db
def test_unverified_client_cannot_login(client, db):
    User.objects.create_user(email="x@example.com", password="Str0ng-Passw0rd!x", full_name="X")
    resp = client.post(reverse("accounts:login"), {"username": "x@example.com", "password": "Str0ng-Passw0rd!x"})
    assert resp.status_code == 200 and b"verify your email" in resp.content


@pytest.mark.django_db
def test_lockout_after_failed_attempts(client, client_user, settings):
    for _ in range(settings.AXES_FAILURE_LIMIT):
        client.post(reverse("accounts:login"), {"username": client_user.email, "password": "wrong-password-1!"})
    resp = client.post(reverse("accounts:login"), {"username": client_user.email, "password": "Str0ng-Passw0rd!x"})
    assert resp.status_code == 403 or b"Too many" in resp.content


@pytest.mark.django_db
def test_mfa_enforced_for_approver(client, approver):
    client.force_login(approver)
    resp = client.get(reverse("lic:application_list"))
    assert resp.status_code == 302 and reverse("accounts:mfa_setup") in resp["Location"]


@pytest.mark.django_db
def test_api_key_roundtrip(client_user):
    key, raw = APIKey.generate(client_user, "lab", scopes=["submissions:write"])
    assert raw.startswith("wsk_") and key.key_hash == APIKey.hash_key(raw)
    assert key.is_active


@pytest.mark.django_db
def test_subject_access_export(client, client_user):
    client.force_login(client_user)
    resp = client.get(reverse("accounts:my_data_export"))
    assert resp.status_code == 200 and resp.json()["account"]["email"] == client_user.email
