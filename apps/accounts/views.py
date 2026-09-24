from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core import audit
from apps.core.notifications import notify

from . import roles
from .forms import LoginForm, RegistrationForm, TOTPTokenForm
from .models import EmailToken, PasswordHistory


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        audit.log("auth.login", self.request.user, actor=self.request.user)
        return response


class LogoutView(auth_views.LogoutView):
    pass


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("core:home")

    def form_valid(self, form):
        PasswordHistory.objects.create(user=self.request.user, password=self.request.user.password)
        response = super().form_valid(form)
        audit.log("auth.password_changed", self.request.user)
        return response


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/password_reset_email.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("accounts:password_reset_complete")

    def form_valid(self, form):
        PasswordHistory.objects.create(user=self.user, password=self.user.password)
        response = super().form_valid(form)
        audit.log("auth.password_reset", self.user, actor=self.user)
        return response


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


@require_http_methods(["GET", "POST"])
def register(request):
    if request.user.is_authenticated:
        return redirect("core:home")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.groups.add(Group.objects.get_or_create(name=roles.CLIENT)[0])
        token = EmailToken.issue(user)
        link = settings.SITE_URL + reverse("accounts:verify", args=[token.token])
        notify(user, "Verify your WaterSource Jamaica account", f"Welcome. Confirm your email by opening this link within 24 hours:\n{link}")
        audit.log("auth.registered", user, actor=user)
        return render(request, "accounts/register_done.html")
    return render(request, "accounts/register.html", {"form": form})


def verify_email(request, token):
    t = get_object_or_404(EmailToken, token=token, purpose=EmailToken.PURPOSE_VERIFY)
    if not t.is_valid:
        return render(request, "accounts/verify_failed.html", status=400)
    t.used_at = timezone.now()
    t.save(update_fields=["used_at"])
    if t.user.email_verified_at is None:
        t.user.email_verified_at = timezone.now()
        t.user.save(update_fields=["email_verified_at"])
        audit.log("auth.email_verified", t.user, actor=t.user)
    messages.success(request, "Your email is verified. You can now sign in.")
    return redirect("accounts:login")


@login_required
def mfa_setup(request):
    device = TOTPDevice.objects.filter(user=request.user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=request.user, name="Authenticator app", confirmed=False)
    form = TOTPTokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if device.verify_token(form.cleaned_data["token"]):
            device.confirmed = True
            device.save(update_fields=["confirmed"])
            otp_login(request, device)
            audit.log("auth.mfa_enrolled", request.user)
            messages.success(request, "Two-factor authentication is now active on your account.")
            return redirect("core:home")
        form.add_error("token", "That code was not accepted. Check the time on your phone and try again.")
    return render(request, "accounts/mfa_setup.html", {"form": form, "otpauth_url": device.config_url})


@login_required
def mfa_verify(request):
    devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
    form = TOTPTokenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        for device in devices:
            if device.verify_token(form.cleaned_data["token"]):
                otp_login(request, device)
                audit.log("auth.mfa_verified", request.user)
                return redirect(request.GET.get("next") or "core:home")
        form.add_error("token", "Invalid code.")
        audit.log("auth.mfa_failed", request.user)
    return render(request, "accounts/mfa_verify.html", {"form": form})


@login_required
def profile(request):
    """Data-subject self-service (DPA s.6 rights): see and export what we hold."""
    return render(request, "accounts/profile.html", {"api_keys": request.user.api_keys.filter(revoked_at__isnull=True)})


@login_required
def my_data_export(request):
    """Machine-readable copy of the user's personal data (DPA access right)."""
    from django.http import JsonResponse

    from .services import personal_data_export

    audit.log("dpa.subject_access_export", request.user)
    return JsonResponse(personal_data_export(request.user), json_dumps_params={"indent": 2})
