"""M87 — Odysseus workspace shell, settings, proxy (P0–P1)."""
from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_odysseus import OdysseusSettingsForm
from delayu.mixins import ModulePermissionMixin
from delayu.services.access import user_can
from delayu.services.odysseus_invest import SESSION_KEY
from delayu.services.odysseus_settings import check_odysseus_health, ensure_odysseus_settings
from delayu.services.scope import is_platform_admin
from delayu.views_platform import _ctx_membership


class OdysseusShellView(ModulePermissionMixin, TemplateView):
    module_code = "M87"
    template_name = "platform/ai/odysseus_shell.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        cfg = ensure_odysseus_settings(m.subsystem)
        ctx["page_title"] = "Odysseus"
        ctx["ai_tab"] = "odysseus"
        ctx["config"] = cfg
        ctx["can_manage"] = is_platform_admin(self.request.user) or user_can(
            self.request.user, "M87", "change"
        )
        ctx["invest_context"] = self.request.session.get(SESSION_KEY)
        ctx["workspace_href"] = reverse("platform-odysseus-proxy-root")
        if cfg.embed_mode == cfg.EmbedMode.NEW_TAB:
            ctx["workspace_href"] = cfg.base_url
        return ctx


class OdysseusSettingsView(ModulePermissionMixin, TemplateView):
    module_code = "M87"
    required_action = "change"
    template_name = "platform/ai/odysseus_settings.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not (is_platform_admin(request.user) or user_can(request.user, "M87", "change")):
            messages.error(request, "Настройки Odysseus доступны администратору.")
            return redirect("platform-odysseus")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        cfg = ensure_odysseus_settings(m.subsystem)
        ctx["page_title"] = "Odysseus — настройки"
        ctx["ai_tab"] = "odysseus"
        ctx["form"] = kwargs.get("form") or OdysseusSettingsForm(instance=cfg)
        ctx["config"] = cfg
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        cfg = ensure_odysseus_settings(m.subsystem)
        if request.POST.get("action") == "health":
            ok = check_odysseus_health(cfg)
            if ok:
                messages.success(request, "Odysseus отвечает.")
            else:
                messages.warning(request, "Odysseus недоступен по base_url.")
            return redirect("platform-odysseus-settings")
        form = OdysseusSettingsForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, "Настройки Odysseus сохранены.")
            return redirect("platform-odysseus-settings")
        return self.render_to_response(self.get_context_data(form=form))


class OdysseusProxyView(ModulePermissionMixin, View):
    """P1 reverse proxy — allowlisted paths only."""

    module_code = "M87"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        return super().dispatch(request, *args, **kwargs)

    def _forward(self, request, path: str):
        from delayu.services.odysseus_proxy import proxy_request

        m = _ctx_membership(self)
        cfg = ensure_odysseus_settings(m.subsystem)
        if not cfg.enabled:
            return HttpResponseForbidden("Odysseus выключен в настройках подсистемы.")
        try:
            return proxy_request(request, cfg=cfg, path=path or "")
        except PermissionError:
            return HttpResponse(status=404)

    def get(self, request, path=""):
        return self._forward(request, path)

    def post(self, request, path=""):
        return self._forward(request, path)
