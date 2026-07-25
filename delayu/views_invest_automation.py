from __future__ import annotations

import secrets

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.views.generic import TemplateView

from delayu.forms_invest_automation import (
    InvestAutomationConnectionForm,
    InvestAutomationFlagsForm,
    InvestAutomationMappingForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import Subsystem
from delayu.services.access import get_membership_or_403
from delayu.services.invest_automation_access import user_can_manage_invest_automation
from delayu.services.invest_flags import (
    DEFAULT_FIELD_MAPPING_V1,
    DEFAULT_STAGE_MAPPING_V1,
    ensure_automation_config,
)
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = InvestAutomationFlagsForm(initial_flags=ctx["flags"])
        return ctx

    def post(self, request, *args, **kwargs):
        cfg = self.get_config()
        form = InvestAutomationFlagsForm(request.POST, initial_flags=cfg.get_flags())
        if form.is_valid():
            cfg.flags = form.cleaned_flags()
            cfg.save(update_fields=["flags", "updated_at"])
            messages.success(request, "Компоненты сохранены.")
            return redirect("invest-automation-flags")
        ctx = self.get_context_data()
        ctx["form"] = form
        return self.render_to_response(ctx)


class InvestAutomationMappingView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/mapping.html"
    automation_tab = "mapping"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = InvestAutomationMappingForm.from_config(ctx["config"])
        return ctx

    def post(self, request, *args, **kwargs):
        cfg = self.get_config()
        if request.POST.get("action") == "reset":
            cfg.field_mapping = dict(DEFAULT_FIELD_MAPPING_V1)
            cfg.stage_mapping = {k: list(v) for k, v in DEFAULT_STAGE_MAPPING_V1.items()}
            cfg.save(update_fields=["field_mapping", "stage_mapping", "updated_at"])
            messages.success(request, "Mapping сброшен к v1.")
            return redirect("invest-automation-mapping")
        form = InvestAutomationMappingForm(request.POST)
        if form.is_valid():
            fields = form.cleaned_field_mapping()
            stages = form.cleaned_stage_mapping()
            if not fields and not stages:
                messages.warning(request, "Пустой mapping не сохранён — используйте сброс к defaults.")
                return redirect("invest-automation-mapping")
            if fields:
                cfg.field_mapping = fields
            if stages:
                cfg.stage_mapping = stages
            cfg.save(update_fields=["field_mapping", "stage_mapping", "updated_at"])
            messages.success(request, "Mapping сохранён.")
            return redirect("invest-automation-mapping")
        ctx = self.get_context_data()
        ctx["form"] = form
        return self.render_to_response(ctx)


class InvestAutomationStatusView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/status.html"
    automation_tab = "status"
