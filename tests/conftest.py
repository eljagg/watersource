import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from apps.accounts import roles
from apps.accounts.models import User, UserType
from apps.ref.models import Parish, Party, PartyKind, Well


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
    with django_db_blocker.unblock():
        call_command("bootstrap_roles", verbosity=0)
        call_command("bootstrap_workflows", verbosity=0)
        call_command("bootstrap_categories", verbosity=0)


def _user(email, role=None, user_type=UserType.STAFF, **kw):
    u = User.objects.create_user(email=email, password="Str0ng-Passw0rd!x", full_name=email.split("@")[0].title(), user_type=user_type, **kw)
    if role:
        u.groups.add(Group.objects.get(name=role))
    return u


@pytest.fixture
def client_user(db):
    from django.utils import timezone

    return _user("client@example.com", roles.CLIENT, UserType.CLIENT, email_verified_at=timezone.now())


@pytest.fixture
def reviewer(db):
    return _user("reviewer@wra.gov.jm", roles.REVIEWER)


@pytest.fixture
def approver(db):
    return _user("approver@wra.gov.jm", roles.APPROVER)


@pytest.fixture
def parish(db):
    return Parish.objects.create(code="STC", name="St. Catherine")


@pytest.fixture
def well(db, parish):
    return Well.objects.create(name="Bog Walk 1", aliases=["BW-1"], parish=parish, easting=760000, northing=650000, approval_state="approved", classification="public")


@pytest.fixture
def party(db):
    return Party.objects.create(kind=PartyKind.APPLICANT, name="Jane Brown", email="jane@example.com", phone="876-000-0000", address="Spanish Town")
