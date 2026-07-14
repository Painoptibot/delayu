"""Кабинет оператора штаба — «Топливный пропуск» (платформа Делаю)."""
from __future__ import annotations

import json

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_fuel import (
    FuelAzsStationForm,
    FuelBlacklistAddForm,
    FuelParityRuleForm,
    FuelPortalSettingsForm,
    FuelRejectForm,
    FuelSupportTicketForm,
)
from delayu.mixins import PlatformLayoutMixin
from delayu.models_fuel import (
    FuelApplication,
    FuelAzsStation,
    FuelBlacklistEntry,
    FuelEventLog,
    FuelRedeem,
    FuelSupportTicket,
)
from delayu.services.access import activate_fuel_membership, membership_can
from delayu.services.fuel import (
    approve_application,
    get_or_create_parity_rule,
    operator_dashboard,
    reject_application,
    resolve_parity_rule,
    save_parity_rule,
    update_azs_stock,
)
from delayu.services.fuel_analytics import add_blacklist_entry, full_dashboard_metrics, leadership_metrics
from delayu.services.fuel_capacity import get_portal_settings
from delayu.services.fuel_events import log_fuel_event, operator_live_payload
from delayu.services.fuel_health import fuel_health_report, run_load_demo
from delayu.services.fuel_security_audit import fuel_security_audit
from delayu.services.fuel_operator_admin import (
    archive_azs_station,
    create_azs_station,
    deactivate_blacklist_entry,
    reactivate_blacklist_entry,
    restore_azs_station,
    toggle_azs_portal_block,
    update_azs_station,
)


def _fuel_membership(view):
    mem = getattr(view.request, "fuel_operator_membership", None)
    if mem:
        return mem
    mem = activate_fuel_membership(view.request.user)
    if not mem:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Нет доступа к контуру «Топливный пропуск»")
    return mem


def _citizen_portal_path(sub) -> str:
    if sub.public_subdomain:
        return f"/fuel/{sub.public_subdomain}/"
    return f"/fuel/{sub.code}/"


class FuelOperatorMixin(LoginRequiredMixin, PlatformLayoutMixin):
    module_code = "M22"
    required_action = "view"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return LoginRequiredMixin.dispatch(self, request, *args, **kwargs)
        membership = activate_fuel_membership(request.user)
        if not membership:
            raise PermissionDenied("Нет доступа к контуру «Топливный пропуск»")
        action = self.required_action
        if request.method == "POST" and self.required_action == "view":
            action = "create"
        if not membership_can(membership, self.module_code, action):
            raise PermissionDenied(f"Нет доступа к {self.module_code}")
        request.fuel_operator_membership = membership
        return super(LoginRequiredMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        from django.conf import settings

        ctx = super().get_context_data(**kwargs)
        m = getattr(self.request, "fuel_operator_membership", None)
        ctx["yandex_metrika_id"] = getattr(settings, "FUEL_YANDEX_METRIKA_ID", "") or ""
        ctx["fuel_metrika_surface"] = "operator"
        if m:
            ctx.setdefault("subsystem", m.subsystem)
        return ctx


class FuelOperatorHubView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/hub.html"
    page_title = "Топливный пропуск"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["stats"] = operator_dashboard(m.subsystem)
        ctx["metrics"] = full_dashboard_metrics(m.subsystem)
        ctx["pending_apps"] = (
            m.subsystem.fuel_applications.filter(status=FuelApplication.Status.PENDING)
            .select_related("citizen", "category")[:10]
        )
        ctx["citizen_portal_path"] = _citizen_portal_path(m.subsystem)
        ctx["live_api_url"] = reverse("fuel-operator-live-api")
        return ctx


class FuelOperatorDashboardView(FuelOperatorMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/fuel/dashboard.html"
    page_title = "Дашборд штаба"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        metrics = full_dashboard_metrics(m.subsystem)
        ctx["metrics"] = metrics
        ctx["map_points_json"] = json.dumps(metrics["map_points"], ensure_ascii=False)
        ctx["map_center_json"] = json.dumps(metrics["map_center"])
        ctx["metrics_api_url"] = reverse("fuel-operator-metrics-api")
        return ctx


class FuelOperatorLeadershipView(FuelOperatorMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/fuel/leadership.html"
    page_title = "Руководство — сводка"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        metrics = leadership_metrics(m.subsystem)
        ctx["metrics"] = metrics
        ctx["map_points_json"] = json.dumps(metrics["map_points_json"], ensure_ascii=False)
        return ctx


class FuelOperatorApplicationsView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/applications.html"
    page_title = "Заявки на пропуск"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        status = self.request.GET.get("status", "")
        qs = m.subsystem.fuel_applications.select_related(
            "citizen", "category", "assigned_azs", "permit"
        ).prefetch_related(
            Prefetch(
                "permit__redeems",
                queryset=FuelRedeem.objects.select_related("azs").order_by("-created_at"),
            )
        )
        if status:
            qs = qs.filter(status=status)
        ctx["applications"] = qs.order_by("-created_at")[:200]
        ctx["filter_status"] = status
        ctx["live_api_url"] = reverse("fuel-operator-live-api")
        return ctx


class FuelOperatorApproveView(FuelOperatorMixin, View):
    required_action = "change"

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        app = get_object_or_404(FuelApplication, pk=pk, subsystem=m.subsystem)
        if app.status != FuelApplication.Status.PENDING:
            messages.warning(request, "Заявка уже обработана.")
        else:
            permit = approve_application(app)
            log_fuel_event(
                m.subsystem,
                FuelEventLog.Channel.OPERATOR,
                "application.approve",
                f"Одобрена заявка {app.number}, пропуск {permit.number}",
                user=request.user,
                object_type="FuelApplication",
                object_id=app.pk,
                payload={"permit_id": permit.pk, "plate": app.plate},
                request=request,
            )
            messages.success(request, f"Одобрено. Пропуск {permit.number}.")
        return redirect("fuel-operator-applications")


class FuelOperatorRejectView(FuelOperatorMixin, TemplateView):
    required_action = "change"
    template_name = "platform/fuel/reject.html"
    page_title = "Отклонение заявки"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["application"] = get_object_or_404(
            FuelApplication, pk=self.kwargs["pk"], subsystem=m.subsystem
        )
        ctx["form"] = FuelRejectForm()
        return ctx

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        app = get_object_or_404(FuelApplication, pk=pk, subsystem=m.subsystem)
        form = FuelRejectForm(request.POST)
        if form.is_valid():
            reject_application(app, form.cleaned_data["reason"])
            log_fuel_event(
                m.subsystem,
                FuelEventLog.Channel.OPERATOR,
                "application.reject",
                f"Отклонена заявка {app.number}",
                user=request.user,
                object_type="FuelApplication",
                object_id=app.pk,
                payload={"reason": form.cleaned_data["reason"], "plate": app.plate},
                request=request,
            )
            messages.success(request, "Заявка отклонена.")
            return redirect("fuel-operator-applications")
        return self.render_to_response(self.get_context_data(form=form))


class FuelOperatorAzsView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/azs.html"
    page_title = "АЗС"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["stations"] = m.subsystem.fuel_azs_stations.order_by("is_archived", "name")
        ctx["active_stations"] = ctx["stations"].filter(is_archived=False)
        ctx["archived_stations"] = ctx["stations"].filter(is_archived=True)
        ctx["citizen_portal_azs_path"] = _citizen_portal_path(m.subsystem) + "azs/login/"
        ctx["live_api_url"] = reverse("fuel-operator-live-api")
        return ctx


class FuelOperatorAzsToggleView(FuelOperatorMixin, View):
    required_action = "change"

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        station = get_object_or_404(FuelAzsStation, pk=pk, subsystem=m.subsystem)
        station.is_accepting_permits = not station.is_accepting_permits
        station.save(update_fields=["is_accepting_permits"])
        state = "включён" if station.is_accepting_permits else "остановлен"
        message = f"Приём пропусков на {station.name}: {state}."
        log_fuel_event(
            m.subsystem,
            FuelEventLog.Channel.OPERATOR,
            "azs.toggle_accepting",
            message,
            user=request.user,
            azs=station,
            object_type="FuelAzsStation",
            object_id=station.pk,
            payload={"is_accepting_permits": station.is_accepting_permits},
            request=request,
        )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "station_id": station.pk,
                    "station_name": station.name,
                    "is_accepting_permits": station.is_accepting_permits,
                    "message": message,
                }
            )
        messages.success(request, message)
        return redirect(request.POST.get("next") or "fuel-operator-azs")


class FuelOperatorMetricsApiView(FuelOperatorMixin, View):
    module_code = "M15"

    def get(self, request):
        m = _fuel_membership(self)
        metrics = full_dashboard_metrics(m.subsystem)
        return JsonResponse(
            {
                "ok": True,
                "updated_at": metrics["updated_at"].isoformat(),
                "avg_queue_minutes": metrics["avg_queue_minutes"],
                "empty_azs_count": metrics["empty_azs_count"],
                "denials_today": metrics["denials_today"],
                "gap_pct": metrics["gap_pct"],
                "map_points": metrics["map_points"],
            }
        )


class FuelOperatorBlacklistView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/blacklist.html"
    page_title = "Чёрный список"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["entries"] = FuelBlacklistEntry.objects.filter(
            subsystem=m.subsystem,
        ).order_by("-is_active", "-created_at")[:200]
        ctx["form"] = kwargs.get("form") or FuelBlacklistAddForm()
        return ctx

    def post(self, request):
        m = _fuel_membership(self)
        form = FuelBlacklistAddForm(request.POST)
        if form.is_valid():
            try:
                entry = add_blacklist_entry(
                    m.subsystem,
                    plate=form.cleaned_data.get("plate", ""),
                    inn=form.cleaned_data.get("inn", ""),
                    reason=form.cleaned_data["reason"],
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                log_fuel_event(
                    m.subsystem,
                    FuelEventLog.Channel.OPERATOR,
                    "blacklist.add",
                    f"Добавлено в чёрный список: {entry.plate or entry.inn}",
                    user=request.user,
                    object_type="FuelBlacklistEntry",
                    object_id=entry.pk,
                    payload={"plate": entry.plate, "inn": entry.inn},
                    request=request,
                )
                messages.success(request, "Запись добавлена в чёрный список.")
                return redirect("fuel-operator-blacklist")
        return self.render_to_response(self.get_context_data(form=form), status=400)


class FuelOperatorReportsView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/reports.html"
    page_title = "Отчёты"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["stats"] = operator_dashboard(m.subsystem)
        ctx["recent_redeems"] = (
            FuelRedeem.objects.filter(subsystem=m.subsystem)
            .select_related("azs", "permit")
            .order_by("-created_at")[:50]
        )
        return ctx


class FuelOperatorParityView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/parity.html"
    page_title = "Чётность госномеров"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        rule = get_or_create_parity_rule(m.subsystem)
        preview = resolve_parity_rule(m.subsystem)
        ctx["form"] = kwargs.get("form") or FuelParityRuleForm(
            initial={
                "is_enabled": rule.is_enabled,
                "mode": rule.mode,
                "message": rule.message,
            }
        )
        ctx["preview"] = preview
        ctx["rule"] = rule
        return ctx

    def post(self, request):
        m = _fuel_membership(self)
        form = FuelParityRuleForm(request.POST)
        if form.is_valid():
            save_parity_rule(
                m.subsystem,
                is_enabled=form.cleaned_data["is_enabled"],
                mode=form.cleaned_data["mode"],
                message=form.cleaned_data.get("message", ""),
            )
            log_fuel_event(
                m.subsystem,
                FuelEventLog.Channel.OPERATOR,
                "parity.save",
                "Обновлены настройки чётности госномеров",
                user=request.user,
                object_type="FuelParityRule",
                object_id=m.subsystem.pk,
                payload=form.cleaned_data,
                request=request,
            )
            messages.success(request, "Настройки уведомления сохранены.")
            return redirect("fuel-operator-parity")
        return self.render_to_response(self.get_context_data(form=form), status=400)


class FuelOperatorLiveApiView(FuelOperatorMixin, View):
    """Онлайн-снимок заявок, отпусков и АЗС для панели оператора."""

    def get(self, request):
        m = _fuel_membership(self)
        return JsonResponse(operator_live_payload(m.subsystem))


class FuelOperatorAzsCreateView(FuelOperatorMixin, TemplateView):
    required_action = "change"
    template_name = "platform/fuel/azs_form.html"
    page_title = "Новая АЗС"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = kwargs.get("form") or FuelAzsStationForm()
        ctx["is_create"] = True
        return ctx

    def post(self, request):
        m = _fuel_membership(self)
        form = FuelAzsStationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data.copy()
            data["code"] = form.cleaned_data.get("code", "")
            create_azs_station(m.subsystem, data, user=request.user, request=request)
            messages.success(request, "АЗС добавлена.")
            return redirect("fuel-operator-azs")
        return self.render_to_response(self.get_context_data(form=form), status=400)


class FuelOperatorAzsEditView(FuelOperatorMixin, TemplateView):
    required_action = "change"
    template_name = "platform/fuel/azs_form.html"
    page_title = "Редактирование АЗС"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        station = get_object_or_404(FuelAzsStation, pk=self.kwargs["pk"], subsystem=m.subsystem)
        ctx["station"] = station
        ctx["form"] = kwargs.get("form") or FuelAzsStationForm(
            instance=station, initial={"code": station.code}
        )
        ctx["is_create"] = False
        return ctx

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        station = get_object_or_404(FuelAzsStation, pk=pk, subsystem=m.subsystem)
        form = FuelAzsStationForm(request.POST, instance=station)
        if form.is_valid():
            update_azs_station(station, form.cleaned_data, user=request.user, request=request)
            messages.success(request, "Изменения сохранены.")
            return redirect("fuel-operator-azs")
        return self.render_to_response(self.get_context_data(form=form), status=400)


class FuelOperatorAzsArchiveView(FuelOperatorMixin, View):
    required_action = "change"

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        station = get_object_or_404(FuelAzsStation, pk=pk, subsystem=m.subsystem)
        if station.is_archived:
            restore_azs_station(station, user=request.user, request=request)
            messages.success(request, f"АЗС «{station.name}» восстановлена.")
        else:
            archive_azs_station(station, user=request.user, request=request)
            messages.success(request, f"АЗС «{station.name}» перенесена в архив.")
        return redirect(request.POST.get("next") or "fuel-operator-azs")


class FuelOperatorAzsPortalBlockView(FuelOperatorMixin, View):
    required_action = "change"

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        station = get_object_or_404(FuelAzsStation, pk=pk, subsystem=m.subsystem)
        toggle_azs_portal_block(station, user=request.user, request=request)
        state = "заблокирован" if station.portal_blocked else "разблокирован"
        message = f"Портал АЗС «{station.name}»: доступ {state}."
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "station_id": station.pk,
                    "portal_blocked": station.portal_blocked,
                    "message": message,
                }
            )
        messages.success(request, message)
        return redirect("fuel-operator-azs")


class FuelOperatorBlacklistDeactivateView(FuelOperatorMixin, View):
    required_action = "change"

    def post(self, request, pk: int):
        m = _fuel_membership(self)
        entry = get_object_or_404(FuelBlacklistEntry, pk=pk, subsystem=m.subsystem)
        if entry.is_active:
            deactivate_blacklist_entry(entry, user=request.user, request=request)
            messages.success(request, "Ограничение снято. Запись остаётся в журнале.")
        else:
            reactivate_blacklist_entry(entry, user=request.user, request=request)
            messages.success(request, "Ограничение восстановлено.")
        return redirect("fuel-operator-blacklist")


class FuelOperatorLogsOperationsView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/logs_operations.html"
    page_title = "Журнал операций (штаб и АЗС)"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["events"] = (
            FuelEventLog.objects.filter(
                subsystem=m.subsystem,
                channel__in=[FuelEventLog.Channel.OPERATOR, FuelEventLog.Channel.AZS],
            )
            .select_related("user", "azs", "citizen")
            .order_by("-created_at")[:300]
        )
        return ctx


class FuelOperatorLogsCitizenView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/logs_citizen.html"
    page_title = "Журнал портала жителя"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["events"] = (
            FuelEventLog.objects.filter(
                subsystem=m.subsystem,
                channel=FuelEventLog.Channel.CITIZEN,
            )
            .select_related("citizen")
            .order_by("-created_at")[:300]
        )
        return ctx


class FuelOperatorSupportView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/support.html"
    page_title = "Обращения в техподдержку"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        status = self.request.GET.get("status", "")
        qs = FuelSupportTicket.objects.filter(subsystem=m.subsystem).select_related("citizen")
        if status:
            qs = qs.filter(status=status)
        ctx["tickets"] = qs.order_by("-created_at")[:200]
        ctx["status_filter"] = status
        ctx["status_choices"] = FuelSupportTicket.Status.choices
        return ctx


class FuelOperatorSupportDetailView(FuelOperatorMixin, TemplateView):
    template_name = "platform/fuel/support_detail.html"
    page_title = "Обращение в ТП"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ticket = get_object_or_404(
            FuelSupportTicket.objects.select_related("citizen"),
            pk=kwargs["pk"],
            subsystem=m.subsystem,
        )
        ctx["ticket"] = ticket
        ctx["form"] = kwargs.get("form") or FuelSupportTicketForm(
            initial={"status": ticket.status, "operator_note": ticket.operator_note}
        )
        return ctx

    def post(self, request, pk):
        m = _fuel_membership(self)
        ticket = get_object_or_404(FuelSupportTicket, pk=pk, subsystem=m.subsystem)
        form = FuelSupportTicketForm(request.POST)
        if form.is_valid():
            ticket.status = form.cleaned_data["status"]
            ticket.operator_note = form.cleaned_data["operator_note"]
            ticket.save(update_fields=["status", "operator_note", "updated_at"])
            log_fuel_event(
                m.subsystem,
                FuelEventLog.Channel.OPERATOR,
                "support.respond",
                f"Ответ на обращение #{ticket.pk} · {ticket.name}",
                user=request.user,
                citizen=ticket.citizen,
                object_type="FuelSupportTicket",
                object_id=ticket.pk,
                request=request,
            )
            messages.success(request, "Ответ сохранён")
            return redirect("fuel-operator-support")
        ctx = self.get_context_data(pk=pk, form=form)
        return self.render_to_response(ctx, status=400)


class FuelOperatorSettingsView(FuelOperatorMixin, TemplateView):
    module_code = "M22"
    template_name = "platform/fuel/settings.html"
    page_title = "Настройки прогноза загрузки"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        settings_obj = get_portal_settings(m.subsystem)
        ctx["form"] = kwargs.get("form") or FuelPortalSettingsForm(instance=settings_obj)
        ctx["portal_settings"] = settings_obj
        return ctx

    def post(self, request):
        m = _fuel_membership(self)
        settings_obj = get_portal_settings(m.subsystem)
        form = FuelPortalSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            log_fuel_event(
                m.subsystem,
                FuelEventLog.Channel.OPERATOR,
                "settings.update",
                "Обновлены настройки прогноза загрузки",
                user=request.user,
                request=request,
                payload=form.cleaned_data,
            )
            messages.success(request, "Настройки сохранены")
            return redirect("fuel-operator-settings")
        ctx = self.get_context_data(form=form)
        return self.render_to_response(ctx, status=400)


class FuelOperatorDemoView(FuelOperatorMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/fuel/demo.html"
    page_title = "Нагрузка и состояние системы"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["health"] = fuel_health_report(m.subsystem)
        ctx["load_result"] = self.request.session.pop("fuel_load_result", None)
        return ctx

    def post(self, request):
        m = _fuel_membership(self)
        requests_n = min(100, max(5, int(request.POST.get("requests", 20))))
        workers = min(32, max(1, int(request.POST.get("workers", 8))))
        result = run_load_demo(m.subsystem, requests_per_endpoint=requests_n, workers=workers)
        request.session["fuel_load_result"] = result
        log_fuel_event(
            m.subsystem,
            FuelEventLog.Channel.OPERATOR,
            "demo.load_test",
            f"Нагрузочный тест: {result['total_requests']} запросов, p95 {result['p95_ms']} мс",
            user=request.user,
            request=request,
            payload={"rps": result["rps"], "p95_ms": result["p95_ms"]},
        )
        messages.info(request, "Нагрузочный тест завершён")
        return redirect("fuel-operator-demo")


class FuelOperatorSecurityView(FuelOperatorMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/fuel/security.html"
    page_title = "Аудит безопасности"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _fuel_membership(self)
        ctx["audit"] = fuel_security_audit(m.subsystem)
        return ctx

