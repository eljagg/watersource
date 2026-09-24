import re

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class ComplexityValidator:
    """At least three of: lower, upper, digit, symbol (ToR H.iii minimum complexity)."""

    def validate(self, password, user=None):
        classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
        if classes < 3:
            raise ValidationError(
                "Use at least three of: lowercase letters, uppercase letters, digits and symbols.",
                code="password_complexity",
            )

    def get_help_text(self):
        return "Your password must contain at least three of: lowercase, uppercase, digits, symbols."


class PasswordHistoryValidator:
    def __init__(self, history=10):
        self.history = history

    def validate(self, password, user=None):
        if user is None or user.pk is None:
            return
        for entry in user.password_history.all()[: self.history]:
            if check_password(password, entry.password):
                raise ValidationError(f"You cannot reuse any of your last {self.history} passwords.", code="password_reused")

    def get_help_text(self):
        return f"You cannot reuse any of your last {self.history} passwords."
