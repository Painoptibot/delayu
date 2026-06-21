"""#15 — подтверждение пароля перед критичными операциями."""
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse

from delayu.services import audit
from delayu.services.reauth import mark_reauth, verify_reauth
from delayu.services.security_policy import profile_for
from delayu.services.totp import profile_totp_enabled
from delayu.views_auth import AuthView


class ReauthConfirmView(AuthView):
    template_name = "auth/reauth_confirm.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["next_url"] = self.request.GET.get("next") or reverse("platform-home")
        profile = profile_for(self.request.user)
        ctx["needs_totp"] = profile_totp_enabled(profile)
        return ctx

    def post(self, request):
        password = request.POST.get("password", "")
        totp_code = request.POST.get("totp_code", "")
        ok, err = verify_reauth(request.user, password, totp_code=totp_code)
        if not ok:
            messages.error(request, err)
            return redirect(request.get_full_path())
        mark_reauth(request)
        from delayu.menu import get_active_membership

        m = get_active_membership(request.user)
        if m:
            audit.log_action(
                request.user,
                m.subsystem,
                "security.reauth",
                "User",
                request.user.pk,
                request=request,
            )
        messages.success(request, "Подтверждение принято (5 мин).")
        return redirect(request.POST.get("next") or request.GET.get("next") or reverse("platform-home"))
