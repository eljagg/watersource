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


def _user(email, role=None, user_type=UserType.STAFF, unit=None, **kw):
    """Create a user; ``unit`` is a WRA unit code (v0.6.0: staff act only on data their unit owns, so staff fixtures need one)."""
    from apps.accounts.models import Unit

    u = User.objects.create_user(email=email, password="Str0ng-Passw0rd!x", full_name=email.split("@")[0].title(), user_type=user_type, **kw)
    if role:
        u.groups.add(Group.objects.get(name=role))
    if unit:
        u.unit = Unit.objects.get(code=unit)
        u.save(update_fields=["unit"])
    return u


@pytest.fixture
def client_user(db):
    from django.utils import timezone

    return _user("client@example.com", roles.CLIENT, UserType.CLIENT, email_verified_at=timezone.now())


@pytest.fixture
def reviewer(db):
    return _user("reviewer@wra.gov.jm", roles.REVIEWER, unit="PLU")  # Permits & Licences: owns applications and abstraction returns


@pytest.fixture
def approver(db):
    return _user("approver@wra.gov.jm", roles.APPROVER, unit="PLU")


@pytest.fixture
def parish(db):
    return Parish.objects.get_or_create(code="STC", defaults={"name": "St. Catherine"})[0]


@pytest.fixture
def well(db, parish):
    return Well.objects.create(name="Bog Walk 1", aliases=["BW-1"], parish=parish, easting=760000, northing=650000, approval_state="approved", classification="public")


@pytest.fixture
def party(db):
    return Party.objects.create(kind=PartyKind.APPLICANT, name="Jane Brown", email="jane@example.com", phone="876-000-0000", address="Spanish Town")


@pytest.fixture(autouse=True)
def _clear_cache():
    """Start every test with an empty cache (branding row, bi refresh stamps, locks)."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()
