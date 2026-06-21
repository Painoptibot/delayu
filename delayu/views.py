from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.generic import TemplateView

from web_project.views import SystemView

from delayu.mixins import PlatformLayoutMixin
from delayu.views_auth import AuthView

# Re-export platform views
from delayu.views_platform import *  # noqa: F401, F403
from delayu.views_users import *  # noqa: F401, F403
from delayu.views_roles import *  # noqa: F401, F403
from delayu.views_structure import *  # noqa: F401, F403
from delayu.views_m01 import *  # noqa: F401, F403
from delayu.views_archive import *  # noqa: F401, F403
from delayu.views_documents import *  # noqa: F401, F403
from delayu.views_workplace import *  # noqa: F401, F403
from delayu.views_help import *  # noqa: F401, F403
from delayu.views_analytics import *  # noqa: F401, F403
from delayu.views_cases import *  # noqa: F401, F403
from delayu.views_registries import *  # noqa: F401, F403
from delayu.views_correspondence import *  # noqa: F401, F403
from delayu.views_bpm import *  # noqa: F401, F403
from delayu.views_comms import *  # noqa: F401, F403
from delayu.views_integrations import *  # noqa: F401, F403
from delayu.views_audio import *  # noqa: F401, F403
from delayu.views_ai import *  # noqa: F401, F403
from delayu.views_infra import *  # noqa: F401, F403
from delayu.views_operations import *  # noqa: F401, F403
from delayu.views_exploitation import *  # noqa: F401, F403
from delayu.views_ux import *  # noqa: F401, F403
from delayu.views_waves import *  # noqa: F401, F403
from delayu.views_studio import *  # noqa: F401, F403
from delayu.views_uzhv import *  # noqa: F401, F403
from delayu.views_security import *  # noqa: F401, F403
from delayu.views_reauth import *  # noqa: F401, F403
from delayu.views_etl import *  # noqa: F401, F403
from delayu.views_sso import *  # noqa: F401, F403


class LoginView(AuthView):
    template_name = "auth/login.html"

    @method_decorator(ensure_csrf_cookie)
    @method_decorator(csrf_protect)
    @method_decorator(never_cache)
    def dispatch(self, request, *args, **kwargs):
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from delayu.services.sso import active_sso_providers

        ctx["sso_providers"] = list(active_sso_providers())
        return ctx

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("platform-home")
        return super().get(request)

    def post(self, request):
        username = request.POST.get("email-username", "").strip()
        password = request.POST.get("password", "")
        if not username or not password:
            messages.error(request, "Введите логин и пароль.")
            return redirect("login")

        user = authenticate(request, username=username, password=password)
        if user is None:
            from delayu.services.security_policy import log_failed_login

            log_failed_login(username, request)
            messages.error(request, "Неверный логин или пароль.")
            return redirect("login")

        login(request, user)
        from delayu.menu import ensure_superuser_membership

        ensure_superuser_membership(user)
        from delayu.services.security_policy import check_login_allowed, profile_for, requires_2fa
        from delayu.services.totp import profile_totp_enabled

        allowed, reason = check_login_allowed(user)
        profile = profile_for(user)
        from delayu.utils_redirect import safe_next_url

        next_url = safe_next_url(request, request.POST.get("next"))

        if reason == "must_change_password":
            messages.warning(request, "Требуется смена пароля. Обратитесь к администратору.")
        if profile_totp_enabled(profile):
            request.session["2fa_verified"] = False
            from delayu.services.session_registry import register_session

            register_session(request)
            messages.info(request, "Введите код из приложения-аутентификатора.")
            return redirect(f"{reverse('two-factor-verify')}?next={next_url}")
        if requires_2fa(user) and not profile_totp_enabled(profile):
            messages.warning(request, "Для вашей роли необходимо включить 2FA.")
            return redirect("two-factor-setup")
        request.session["2fa_verified"] = True
        from delayu.services.session_registry import register_session

        register_session(request)
        return redirect(next_url)


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def tz_download(request):
    from django.http import FileResponse

    from delayu.tz_docs import tz_file_path

    path = tz_file_path()
    if not path.is_file():
        from django.http import Http404

        raise Http404()
    return FileResponse(path.open("rb"), as_attachment=True, filename=path.name)


@login_required
def switch_subsystem(request):
    from delayu.models import SubsystemMembership

    if request.method != "POST":
        return redirect("platform-home")
    mid = request.POST.get("membership_id")
    membership = get_object_or_404(SubsystemMembership, pk=mid, user=request.user)
    SubsystemMembership.objects.filter(user=request.user).update(is_default=False)
    membership.is_default = True
    membership.save(update_fields=["is_default"])
    messages.success(request, f"Активный контур: {membership.subsystem.name}")
    return redirect("platform-home")


handler404 = SystemView.as_view(template_name="pages_misc_error.html", status=404)
handler403 = SystemView.as_view(template_name="pages_misc_not_authorized.html", status=403)
