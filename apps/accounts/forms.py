"""Forms for self-registration, login and TOTP entry (ToR H.i–H.iv)."""
from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from .models import User, UserType


class RegistrationForm(forms.ModelForm):
    """Client self-registration: email, name, organisation, password and privacy-notice acceptance."""
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput, help_text=password_validation.password_validators_help_text_html())
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)
    accept_privacy = forms.BooleanField(label="I have read the privacy notice and agree to the processing of my personal data for licence and data-submission purposes.")

    class Meta:
        model = User
        fields = ["full_name", "email", "phone", "organisation"]

    def clean_email(self):
        """Lower-case the email and reject one already in use."""
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email=email).exists():
            # Enumeration-safe message: same wording as success path in the view
            raise forms.ValidationError("If this address is valid you will receive an email shortly.")
        return email

    def clean(self):
        """Require the privacy notice to be accepted (DPA 2020)."""
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            tmp = User(email=cleaned.get("email", ""), full_name=cleaned.get("full_name", ""))
            password_validation.validate_password(p1, tmp)
        return cleaned

    def save(self, commit=True):
        """Create an inactive-until-verified client account with the chosen password."""
        from django.utils import timezone

        user = super().save(commit=False)
        user.user_type = UserType.CLIENT
        user.set_password(self.cleaned_data["password1"])
        user.privacy_notice_accepted_at = timezone.now()
        user.is_active = True
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """Login by email; wraps Django's form so axes lockout messages surface."""
    username = forms.EmailField(label="Email")

    def confirm_login_allowed(self, user):
        """Block accounts whose email is not yet verified."""
        super().confirm_login_allowed(user)
        if user.is_client and user.email_verified_at is None:
            raise forms.ValidationError("Please verify your email address first.", code="unverified")


class TOTPTokenForm(forms.Form):
    """Six-digit TOTP code entry for MFA setup and verification."""
    token = forms.CharField(label="6-digit code", max_length=8, min_length=6)
