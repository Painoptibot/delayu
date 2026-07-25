from __future__ import annotations

import secrets

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
from django.views.generic import TemplateView

from delayu.forms_invest_automation import (
    InvestAutomationConnectionForm,
    InvestAutomationFlagsForm,
    InvestAutomationMappingForm,
    InvestEscalationRulesForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import Subsystem
from delayu.models_invest import InvestExternalTask, InvestIntegrationEvent
from delayu.services.access import get_membership_or_403
from delayu.services.invest_automation_access import user_can_manage_invest_automation
from delayu.services.invest_bitrix import InvestBitrixError, ingest_bitrix_webhook
from delayu.services.invest_flags import (
    DEFAULT_FIELD_MAPPING_V1,
    DEFAULT_STAGE_MAPPING_V1,
    ensure_automation_config,
)
from delayu.services.invest_journal import requeue_dead_letters, requeue_integration_event
from delayu.services.invest_metrics import collect_metrics
from delayu.services.invest_pipeline import run_scheduled_automation
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
            messages.success(request, "Токен регенерирован. Обновите его в Bitrix и удалите старое значение.")
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

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        channel = self.request.GET.get("channel") or ""
        status = self.request.GET.get("status") or ""

        events = InvestIntegrationEvent.objects.filter(subsystem=sub)
        if channel:
            events = events.filter(channel=channel)
        if status:
            events = events.filter(status=status)

        ctx["metrics"] = collect_metrics(subsystem=sub)
        ctx["events"] = events.select_related("project")[:50]
        ctx["tasks"] = (
            InvestExternalTask.objects.filter(subsystem=sub)
            .exclude(
                status__in=[
                    InvestExternalTask.Status.CANCELLED,
                    InvestExternalTask.Status.AGREED,
                ]
            )
            .select_related("project", "organization")[:50]
        )
        ctx["filter_channel"] = channel
        ctx["filter_status"] = status
        ctx["channel_choices"] = InvestIntegrationEvent.Channel.choices
        ctx["status_choices"] = InvestIntegrationEvent.Status.choices
        ctx["connector_stubs"] = [
            {"code": "rgis_connector", "name": "РГИС", "enabled": bool(ctx["flags"].get("rgis_connector"))},
            {"code": "isogd_connector", "name": "ИСОГД", "enabled": bool(ctx["flags"].get("isogd_connector"))},
        ]
        return ctx

    def post(self, request, *args, **kwargs):
        sub = self.get_subsystem()
        action = request.POST.get("action")
        if action == "run":
            result = run_scheduled_automation(subsystem=sub)
            messages.success(request, f"Прогон выполнен (run #{result.get('metrics_run_id')}).")
        elif action == "requeue_dead":
            count = requeue_dead_letters(subsystem=sub)
            messages.success(request, f"Dead-letter перепоставлено: {count}.")
        else:
            messages.warning(request, "Неизвестное действие.")
        return redirect("invest-automation-status")


class InvestIntegrationInboxView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/integrations/inbox.html"
    automation_tab = "inbox"
    page_title = "Интеграционный inbox"

    retryable_statuses = (
        InvestIntegrationEvent.Status.ERROR,
        InvestIntegrationEvent.Status.DEAD,
        InvestIntegrationEvent.Status.QUEUED,
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["events"] = (
            InvestIntegrationEvent.objects.filter(
                subsystem=self.get_subsystem(),
                status__in=self.retryable_statuses,
            )
            .select_related("project", "site")
            .order_by("-created_at")[:100]
        )
        return ctx

    def post(self, request, *args, **kwargs):
        event = get_object_or_404(
            InvestIntegrationEvent.objects.filter(subsystem=self.get_subsystem()),
            pk=request.POST.get("event_id"),
        )
        requeue_integration_event(event)
        messages.success(request, f"Событие {event.correlation_id} возвращено в очередь.")
        return redirect("invest-integrations-inbox")


class InvestEscalationRulesView(InvestAutomationAdminMixin, TemplateView):
    template_name = "invest/automation/escalation_rules.html"
    automation_tab = "escalation"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = InvestEscalationRulesForm.from_config(ctx["config"])
        ctx["escalation_rules"] = (ctx["config"].options or {}).get("escalation_rules") or {}
        return ctx

    def post(self, request, *args, **kwargs):
        cfg = self.get_config()
        form = InvestEscalationRulesForm(request.POST)
        if form.is_valid():
            options = dict(cfg.options or {})
            options["escalation_rules"] = form.cleaned_rules()
            cfg.options = options
            cfg.save(update_fields=["options", "updated_at"])
            messages.success(request, "Правила эскалации сохранены.")
            return redirect("invest-escalation-rules")
        ctx = self.get_context_data()
        ctx["form"] = form
        return self.render_to_response(ctx)


class InvestAutomationSimulateView(InvestAutomationAdminMixin, TemplateView):
    automation_tab = "status"

    def post(self, request, *args, **kwargs):
        cfg = self.get_config()
        payload = {
            "ID": "SIM-100",
            "TITLE": "Sandbox simulator deal",
            "UF_INVESTOR": "ООО Симулятор",
            "UF_INDUSTRY": "АПК",
            "UF_MO_CODE": "mo1",
            "STAGE_ID": "NEW",
            "ASSIGNED_BY_ID": "dept",
        }
        try:
            result = ingest_bitrix_webhook(
                subsystem=self.get_subsystem(),
                payload=payload,
                token=cfg.bitrix_webhook_token,
            )
        except InvestBitrixError as exc:
            messages.error(request, f"Симулятор Bitrix не выполнен: {exc}")
        else:
            messages.success(request, f"Симулятор Bitrix создал/обновил проект #{result.get('project_id')}.")
        return redirect("invest-automation-status")
