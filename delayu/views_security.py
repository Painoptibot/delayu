"""Безопасность: TOTP 2FA (#13–14)."""
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View

from delayu.services import audit
from delayu.services.security_policy import profile_for, requires_2fa
from delayu.services.totp import (
    TotpUnavailableError,
    generate_secret,
    profile_totp_enabled,
    provisioning_uri,
    verify_code,
)
from delayu.views_auth import AuthView


class TwoFactorVerifyView(AuthView):
    template_name = "auth/two_factor_verify.html"

    def get(self, request):
        if not request.user.is_authenticated:
            return redirect("login")
        profile = profile_for(request.user)
        if not profile_totp_enabled(profile):
            return redirect("platform-home")
        if request.session.get("2fa_verified"):
            return redirect("platform-home")
        return super().get(request)

    def post(self, request):
        if not request.user.is_authenticated:
            return redirect("login")
        profile = profile_for(request.user)
        if not profile_totp_enabled(profile):
            return redirect("platform-home")
        code = request.POST.get("code", "")
        if verify_code(profile.totp_secret, code):
            request.session["2fa_verified"] = True
            from delayu.menu import get_active_membership

            m = get_active_membership(request.user)
            if m:
                audit.log_action(
                    request.user,
                    m.subsystem,
                    "security.2fa_verified",
                    "User",
                    request.user.pk,
                    request=request,
                )
            messages.success(request, "Двухфакторная проверка пройдена.")
            from delayu.services.session_registry import register_session

            register_session(request)
            from delayu.utils_redirect import safe_next_url

            return redirect(safe_next_url(request, request.GET.get("next")))
        messages.error(request, "Неверный код. Проверьте приложение-аутентификатор.")
        return redirect("two-factor-verify")


class TwoFactorSetupView(AuthView):
    template_name = "auth/two_factor_setup.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["requires_2fa"] = requires_2fa(self.request.user)
        profile = profile_for(self.request.user)
        ctx["profile"] = profile
        try:
            secret = self.request.session.get("totp_setup_secret")
            if not secret and not profile_totp_enabled(profile):
                secret = generate_secret()
                self.request.session["totp_setup_secret"] = secret
            if secret:
                ctx["totp_secret"] = secret
                ctx["totp_uri"] = provisioning_uri(self.request.user, secret)
        except TotpUnavailableError:
            ctx["totp_unavailable"] = True
        return ctx

    def post(self, request, *args, **kwargs):
        profile = profile_for(request.user)
        secret = request.session.get("totp_setup_secret") or (profile.totp_secret if profile else "")
        code = request.POST.get("code", "")
        if not secret or not verify_code(secret, code):
            messages.error(request, "Код не принят. Повторите сканирование и ввод.")
            return redirect("two-factor-setup")
        profile.totp_secret = secret
        profile.two_factor_enabled = True
        profile.save(update_fields=["totp_secret", "two_factor_enabled", "updated_at"])
        request.session.pop("totp_setup_secret", None)
        request.session["2fa_verified"] = True
        from delayu.menu import get_active_membership

        m = get_active_membership(request.user)
        if m:
            audit.log_action(
                request.user,
                m.subsystem,
                "security.2fa_enabled",
                "UserProfile",
                profile.pk,
                request=request,
            )
        messages.success(request, "Двухфакторная аутентификация включена.")
        return redirect("platform-cabinet-security")


class TwoFactorDisableView(LoginRequiredMixin, View):
    def post(self, request):
        profile = profile_for(request.user)
        if not profile or not profile_totp_enabled(profile):
            return redirect("platform-cabinet-security")
        if requires_2fa(request.user):
            messages.error(request, "Для вашей роли 2FA обязательна и не может быть отключена.")
            return redirect("platform-cabinet-security")
        password = request.POST.get("password", "")
        code = request.POST.get("code", "")
        user = authenticate(request, username=request.user.get_username(), password=password)
        if user is None or not verify_code(profile.totp_secret, code):
            messages.error(request, "Неверный пароль или код подтверждения.")
            return redirect("platform-cabinet-security")
        profile.totp_secret = ""
        profile.two_factor_enabled = False
        profile.save(update_fields=["totp_secret", "two_factor_enabled", "updated_at"])
        request.session["2fa_verified"] = True
        from delayu.menu import get_active_membership

        m = get_active_membership(request.user)
        if m:
            audit.log_action(
                request.user,
                m.subsystem,
                "security.2fa_disabled",
                "UserProfile",
                profile.pk,
                request=request,
            )
        messages.success(request, "2FA отключена.")
        return redirect("platform-cabinet-security")
