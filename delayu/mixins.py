from django.contrib.auth.mixins import LoginRequiredMixin

from delayu.menu import build_menu_for_membership, get_active_membership
from delayu.services.access import user_can
from web_project import TemplateLayout


class PlatformLayoutMixin:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        membership = get_active_membership(self.request.user)
        context["active_membership"] = membership
        context["can"] = lambda code, act="view": user_can(self.request.user, code, act)
        from delayu.services.privacy import user_may_view_pii

        context["allow_pii"] = user_may_view_pii(self.request.user, self.request)
        from delayu.services.demo_mode import is_demo_mode

        context["demo_mode"] = is_demo_mode(self.request)
        if membership:
            context["menu_json"] = {"menu": build_menu_for_membership(membership)}
            context.setdefault(
                "breadcrumbs",
                [
                    {"label": membership.subsystem.name, "url": None},
                    {"label": getattr(self, "page_title", "") or "Раздел", "url": None},
                ],
            )
            if membership.subsystem.industry_template == "uzhv":
                from django.conf import settings

                context["uzhv_pwa_enabled"] = True
                context["uzhv_vapid_public_key"] = getattr(
                    settings, "UZHV_VAPID_PUBLIC_KEY", ""
                )
        code = getattr(self, "module_code", "") or ""
        if code:
            from delayu.module_hints import get_module_hint

            context["module_hint"] = get_module_hint(code)
            context["module_hint_code"] = code
            if membership and membership.subsystem.primary_color:
                cfg = dict(context.get("TEMPLATE_CONFIG") or {})
                cfg["primary_color"] = membership.subsystem.primary_color
                context["TEMPLATE_CONFIG"] = cfg
        return TemplateLayout.init(self, context)


class ModulePermissionMixin(LoginRequiredMixin, PlatformLayoutMixin):
    module_code = ""
    required_action = "view"

    def dispatch(self, request, *args, **kwargs):
        if not user_can(request.user, self.module_code, self.required_action):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied(f"Нет доступа к {self.module_code}")
        return super().dispatch(request, *args, **kwargs)


class MethodActionPermissionMixin(ModulePermissionMixin):
    """GET — view, POST — create (переопределите action_map при необходимости)."""

    action_map = None

    def dispatch(self, request, *args, **kwargs):
        action_map = self.action_map or {
            "GET": "view",
            "HEAD": "view",
            "OPTIONS": "view",
            "POST": "create",
            "PUT": "change",
            "PATCH": "change",
            "DELETE": "delete",
        }
        action = action_map.get(request.method, self.required_action)
        if not user_can(request.user, self.module_code, action):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied(f"Нет доступа к {self.module_code}")
        return super(ModulePermissionMixin, self).dispatch(request, *args, **kwargs)


class CriticalReauthMixin:
    """#15 — повторный ввод пароля перед критичными операциями."""

    reauth_on_get = False

    def dispatch(self, request, *args, **kwargs):
        if request.method in ("POST", "DELETE") or self.reauth_on_get:
            from delayu.services.reauth import require_reauth_or_redirect

            redir = require_reauth_or_redirect(request)
            if redir:
                return redir
        return super().dispatch(request, *args, **kwargs)


class PlatformAdminRequiredMixin(LoginRequiredMixin):
    """Глобальные настройки платформы — только superuser (контур ЮГИт)."""

    def dispatch(self, request, *args, **kwargs):
        from delayu.services.scope import is_platform_admin, path_requires_platform_admin

        if path_requires_platform_admin(request.path) and not is_platform_admin(
            request.user
        ):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Раздел доступен только администратору платформы")
        return super().dispatch(request, *args, **kwargs)
