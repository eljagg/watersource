"""
Application-managed identity (ToR H.i–v): no SSO, no Active Directory.

Roles are Django groups with fixed names (see roles.py):
  client · updater · reviewer · approver · administrator
Guests are anonymous users. Stage-bound approver rights come from the
workflow stage's approver group, so a 'hydrogeology' reviewer group can be
added by an administrator without code changes.
"""
import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone

from . import roles


class UserType(models.TextChoices):
    STAFF = "staff", "WRA staff"
    CLIENT = "client", "External client"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("user_type", UserType.CLIENT)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, user_type=UserType.STAFF, email_verified_at=timezone.now())
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=32, blank=True)
    organisation = models.CharField(max_length=150, blank=True)
    user_type = models.CharField(max_length=8, choices=UserType.choices, default=UserType.CLIENT)
    party = models.ForeignKey("ref.Party", null=True, blank=True, on_delete=models.SET_NULL, related_name="accounts")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField("Django admin access", default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(default=timezone.now)
    must_change_password = models.BooleanField(default=False)
    last_activity_at = models.DateTimeField(null=True, blank=True)
    privacy_notice_accepted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    anonymised_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["email"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    # -- roles -------------------------------------------------------------
    @property
    def is_staff_user(self) -> bool:
        return self.user_type == UserType.STAFF

    @property
    def is_client(self) -> bool:
        return self.user_type == UserType.CLIENT

    @property
    def role_names(self) -> set[str]:
        if not hasattr(self, "_role_names"):
            self._role_names = set(self.groups.values_list("name", flat=True))
        return self._role_names

    def has_role(self, *names) -> bool:
        if self.is_superuser:
            return True
        return bool(self.role_names & set(names))

    @property
    def mfa_required(self) -> bool:
        from django.conf import settings

        return self.is_staff_user and (self.is_superuser or self.has_role(*settings.MFA_REQUIRED_GROUPS))

    @property
    def password_expired(self) -> bool:
        from django.conf import settings

        if not self.is_staff_user:
            return False
        age = timezone.now() - self.password_changed_at
        return age > timedelta(days=settings.STAFF_PASSWORD_MAX_AGE_DAYS)

    def set_password(self, raw_password):
        super().set_password(raw_password)
        self.password_changed_at = timezone.now()
        self.must_change_password = False


class PasswordHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_history")
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user_id} @ {self.created_at:%Y-%m-%d}"


class EmailToken(models.Model):
    """Single-use, time-limited token for email verification (ToR H.iv)."""

    PURPOSE_VERIFY = "verify"
    PURPOSES = [(PURPOSE_VERIFY, "Verify email")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    purpose = models.CharField(max_length=16, choices=PURPOSES, default=PURPOSE_VERIFY)
    token = models.CharField(max_length=64, unique=True, default=secrets.token_urlsafe)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.purpose} for {self.user_id}"

    @classmethod
    def issue(cls, user, purpose=PURPOSE_VERIFY, ttl_hours=24):
        return cls.objects.create(user=user, purpose=purpose, expires_at=timezone.now() + timedelta(hours=ttl_hours))

    @property
    def is_valid(self):
        return self.used_at is None and self.expires_at > timezone.now()


class APIKey(models.Model):
    """Hashed, revocable key for system-to-system submission (ToR F.7).
    Only the prefix is stored in clear; the full key is shown once at creation."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="api_keys")
    name = models.CharField(max_length=100)
    prefix = models.CharField(max_length=12, unique=True)
    key_hash = models.CharField(max_length=128)
    scopes = models.JSONField(default=list, blank=True, help_text="e.g. ['submissions:write', 'observations:read']")
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.prefix}…)"

    @property
    def is_active(self):
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > timezone.now())

    @staticmethod
    def hash_key(raw: str) -> str:
        import hashlib

        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def generate(cls, user, name, scopes=None, expires_at=None):
        raw = "wsk_" + secrets.token_urlsafe(32)
        obj = cls.objects.create(
            user=user, name=name, prefix=raw[:12], key_hash=cls.hash_key(raw), scopes=scopes or [], expires_at=expires_at
        )
        return obj, raw


__all__ = ["User", "UserType", "PasswordHistory", "EmailToken", "APIKey", "roles"]
