from __future__ import annotations

import secrets

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.views.generic import TemplateView

from delayu.forms_invest_automation import InvestAutomationConnectionForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import Subsystem
from delayu.services.access import get_membership_or_403
from delayu.services.invest_automation_access import user_can_manage_invest_automation
from delayu.services.invest_flags import ensure_automation_config
from delayu.views_invest import InvestSubsystemMixin


class InvestAutomationAdminMixin(InvestSubsystemMixin, ModulePermissionMixin):
    module_code = "M22"
    automation_tab = "connection"
    page_title = "Автоматизация"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        membership = get_membership_or_403(request)
        if (
            membership.subsystem.industry_template != "invest"
            or membership.subsystem.status != Subsystem.Status.ACTIVE
        ):
            messages.error(request, "Раздел доступен только в активном инвестконтуре. Переключите контур.")
            return redirect("platform-home")
        self._invest_membership = membership
        if not user_can_manage_invest_automation(request.user, membership):
            messages.error(request, "Управление автоматизацией доступно администратору инвестконтура.")
            return redirect("invest-hub")
        return TemplateView.dispatch(self, request, *args, **kwargs)

    def get_config(self):
        return ensure_automation_config(self.get_subsystem())

    def get_webhook_url(self, cfg):
        try:
            webhook_path = reverse("invest-bitrix-webhook", args=[cfg.subsystem.code])
        except NoReverseMatch:
            webhook_path = f"/api/invest/bitrix/webhook/{cfg.subsystem.code}/"
        return self.request.build_absolute_uri(webhook_path)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cfg = self.get_config()
        ctx["page_title"] = self.page_title
        ctx["automation_tab"] = self.automation_tab
        ctx["config"] = cfg
        ctx["flags"] = cfg.get_flags()
        ctx["webhook_url"] = self.get_webhook_url(cfg)
        return ctx


class InvestAutomationConnectionView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/connection.html"
    automation_tab = "connection"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = InvestAutomationConnectionForm(instance=ctx["config"])
        return ctx

    def post(self, request, *args, **kwargs):
        cfg = self.get_config()
        if request.POST.get("action") == "generate_token":
            cfg.bitrix_webhook_token = f"invest-{cfg.subsystem.code}-{secrets.token_urlsafe(12)}"
            cfg.save(update_fields=["bitrix_webhook_token", "updated_at"])
            messages.success(request, "Токен сгенерирован.")
            return redirect("invest-automation")

        form = InvestAutomationConnectionForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, "Подключение сохранено.")
            return redirect("invest-automation")

        ctx = self.get_context_data()
        ctx["form"] = form
        return self.render_to_response(ctx)


class InvestAutomationFlagsView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/flags.html"
    automation_tab = "flags"


class InvestAutomationMappingView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/mapping.html"
    automation_tab = "mapping"


class InvestAutomationStatusView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/status.html"
    automation_tab = "status"
