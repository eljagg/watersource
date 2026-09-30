"""Password validators beyond Django's defaults (ToR H.iii)."""
import re

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError


class ComplexityValidator:
    """At least three of: lower, upper, digit, symbol (ToR H.iii minimum complexity)."""

    def validate(self, password, user=None):
        """Raise ``ValidationError`` when fewer than three character classes are used."""
        classes = sum(bool(re.search(p, password)) for p in (r"[a-z]", r"[A-Z]", r"\d", r"[^\w\s]"))
        if classes < 3:
            raise ValidationError(
                "Use at least three of: lowercase letters, uppercase letters, digits and symbols.",
                code="password_complexity",
            )

    def get_help_text(self):
        """Help text shown on password forms."""
        return "Your password must contain at least three of: lowercase, uppercase, digits, symbols."


class PasswordHistoryValidator:
    """Reject any of the user's last ``history`` passwords."""
    def __init__(self, history=10):
        self.history = history

    def validate(self, password, user=None):
        """Raise ``ValidationError`` if the password matches a stored hash."""
        if user is None or user.pk is None:
            return
        for entry in user.password_history.all()[: self.history]:
            if check_password(password, entry.password):
                raise ValidationError(f"You cannot reuse any of your last {self.history} passwords.", code="password_reused")

    def get_help_text(self):
        """Help text shown on password forms."""
        return f"You cannot reuse any of your last {self.history} passwords."
