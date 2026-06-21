"""SSO login flow (#69)."""
from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View

from delayu.models import SsoProvider
from delayu.services import audit
from delayu.services.sso import SsoError, active_sso_providers, build_authorize_url, resolve_sso_user, validate_callback
from delayu.views_auth import AuthView


class SsoLoginStartView(AuthView):
    def get(self, request, pk):
        provider = get_object_or_404(SsoProvider, pk=pk, is_active=True)
        try:
            url = build_authorize_url(provider, request)
        except SsoError as exc:
            messages.error(request, str(exc))
            return redirect("login")
        return redirect(url)


class SsoCallbackView(AuthView):
    def get(self, request):
        try:
            provider, code = validate_callback(request)
            redirect_uri = request.build_absolute_uri(reverse("sso-callback"))
            user, meta = resolve_sso_user(provider, code, redirect_uri=redirect_uri)
        except SsoError as exc:
            messages.error(request, str(exc))
            return redirect("login")
        login(request, user)
        request.session["2fa_verified"] = True
        request.session.pop("sso_state", None)
        from delayu.services.session_registry import register_session

        register_session(request)
        audit.log_action(
            user,
            provider.subsystem,
            "security.sso_login",
            "SsoProvider",
            provider.pk,
            payload=meta,
            request=request,
        )
        messages.success(request, f"Вход через {provider.name}")
        return redirect("platform-home")
