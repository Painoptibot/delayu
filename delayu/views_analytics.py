"""M15–M21 — аналитика, отчёты, регламентированная отчётность, качество."""
import json

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_analytics import RegulatorySubmissionForm, ReportScheduleForm, ReportTemplateForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import (
    ActivityEvent,
    CaseFile,
    ReportRun,
    ReportSchedule,
    ReportTemplate,
    RegulatoryReportSubmission,
)
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.analytics import (
    chart_cases_by_status,
    chart_cases_trend,
    chart_correspondence_status,
    chart_tasks_by_priority,
    department_analytics,
    kpi_dashboard,
    overdue_monitor,
    quality_metrics,
    run_report_query,
)
from delayu.services.ux import dashboard_widgets_for_user, get_dashboard_layout
from delayu.views_platform import _ctx_membership


class DashboardView(ModulePermissionMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/analytics/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "dashboard"
        ctx["page_title"] = "KPI-дашборд"
        kpi = kpi_dashboard(m.subsystem)
        ctx["kpi"] = kpi
        days = int(self.request.GET.get("days", 30))
        ctx["period_days"] = days
        cases_trend = chart_cases_trend(m.subsystem, days=days)
        tasks_prio = chart_tasks_by_priority(m.subsystem)
        status_chart = chart_cases_by_status(m.subsystem)
        load_rows = run_report_query(m.subsystem, "tasks_by_user").get("rows", [])
        total = kpi["cases_total"] or 0
        completion = round(100 * kpi["cases_done"] / total) if total else 0

        today = timezone.now().date()
        ctx["overdue_cases"] = CaseFile.objects.filter(
            subsystem=m.subsystem,
            is_archived=False,
            due_date__lt=today,
        ).exclude(status=CaseFile.Status.DONE).select_related("assignee")[:8]
        ctx["activity_feed"] = ActivityEvent.objects.filter(
            subsystem=m.subsystem
        ).select_related("actor")[:10]
        ctx["load_by_user"] = load_rows
        layout = get_dashboard_layout(self.request.user, m.subsystem)
        widgets = dashboard_widgets_for_user(self.request.user, m.subsystem)
        ctx["dashboard_layout"] = layout
        ctx["dashboard_json"] = json.dumps(
            {
                "kpi": kpi,
                "completion_pct": completion,
                "cases_trend": cases_trend,
                "tasks_priority": tasks_prio,
                "status_chart": status_chart,
                "load_by_user": load_rows,
            },
            ensure_ascii=False,
        )
        ctx["dashboard_layout_json"] = json.dumps(widgets, ensure_ascii=False)
        return ctx


class ReportsListView(ModulePermissionMixin, TemplateView):
    module_code = "M16"
    template_name = "platform/analytics/reports_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "reports"
        ctx["page_title"] = "Конструктор отчётов"
        ctx["templates"] = ReportTemplate.objects.filter(
            subsystem=m.subsystem, is_active=True
        ).order_by("name")
        ctx["runs"] = ReportRun.objects.filter(
            template__subsystem=m.subsystem
        ).select_related("template", "user")[:20]
        ctx["schedules"] = ReportSchedule.objects.filter(subsystem=m.subsystem).select_related(
            "template", "created_by"
        )[:20]
        ctx["schedule_form"] = ReportScheduleForm(subsystem=m.subsystem)
        ctx["can_create"] = user_can(self.request.user, "M16", "create")
        ctx["can_change"] = user_can(self.request.user, "M16", "change")
        key = self.request.GET.get("run")
        if key:
            period = int(self.request.GET.get("period", 30))
            ctx["result"] = run_report_query(m.subsystem, key, period_days=period)
            tpl = ReportTemplate.objects.filter(subsystem=m.subsystem, query_key=key).first()
            if tpl:
                ReportRun.objects.create(
                    template=tpl,
                    user=self.request.user,
                    result=ctx["result"],
                    period_label=f"{period}d",
                )
            ctx["ran_name"] = (tpl.name if tpl else None) or ctx["result"].get("title", key)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        if not user_can(request.user, "M16", "create"):
            return redirect("platform-reports")
        action = request.POST.get("action", "")
        if action == "run_schedule":
            from delayu.services.report_schedules import run_schedule

            sched = get_object_or_404(ReportSchedule, pk=request.POST.get("pk"), subsystem=m.subsystem)
            run_schedule(sched, user=request.user)
            messages.success(request, f"Отчёт «{sched.template.name}» сформирован по расписанию.")
            return redirect("platform-reports")
        form = ReportScheduleForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            sched = form.save(commit=False)
            sched.subsystem = m.subsystem
            sched.created_by = request.user
            sched.save()
            from delayu.services import audit

            audit.log_action(
                request.user,
                m.subsystem,
                "report.schedule.create",
                "ReportSchedule",
                sched.pk,
                {"template": sched.template.code},
                request,
            )
            messages.success(request, "Расписание сохранено.")
        else:
            messages.error(request, "Проверьте поля расписания.")
        return redirect("platform-reports")


class ReportTemplateModalView(ModulePermissionMixin, View):
    module_code = "M16"

    def get(self, request, pk):
        m = _ctx_membership(self)
        tpl = get_object_or_404(ReportTemplate, pk=pk, subsystem=m.subsystem)
        return render(
            request,
            "platform/analytics/_report_modal.html",
            {
                "tpl": tpl,
                "can_change": user_can(request.user, "M16", "change"),
            },
        )


class ReportTemplateWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M16"
    required_action = "create"
    template_name = "platform/analytics/report_wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый шаблон отчёта"
        ctx["form"] = kwargs.get("form") or ReportTemplateForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ReportTemplateForm(request.POST)
        if form.is_valid():
            tpl = form.save(commit=False)
            tpl.subsystem = m.subsystem
            tpl.save()
            audit.log_action(
                request.user,
                m.subsystem,
                "report_template.create",
                "ReportTemplate",
                tpl.pk,
                {"code": tpl.code},
                request,
            )
            messages.success(request, f"Шаблон «{tpl.name}» создан.")
            return redirect("platform-reports")
        return self.render_to_response(self.get_context_data(form=form))


class RegulatoryReportsView(ModulePermissionMixin, TemplateView):
    module_code = "M17"
    template_name = "platform/analytics/regulatory.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "regulatory"
        ctx["page_title"] = "Регламентированная отчётность"
        ctx["submissions"] = RegulatoryReportSubmission.objects.filter(
            subsystem=m.subsystem
        ).select_related("submitted_by")[:50]
        ctx["form"] = kwargs.get("form") or RegulatorySubmissionForm()
        ctx["can_create"] = user_can(self.request.user, "M17", "create")
        ctx["can_change"] = user_can(self.request.user, "M17", "change")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        action = request.POST.get("action", "create")
        if action == "submit":
            sub = get_object_or_404(
                RegulatoryReportSubmission,
                pk=request.POST.get("pk"),
                subsystem=m.subsystem,
            )
            if user_can(request.user, "M17", "change"):
                sub.status = RegulatoryReportSubmission.Status.SUBMITTED
                sub.submitted_by = request.user
                sub.submitted_at = timezone.now()
                sub.save()
                messages.success(request, "Отчёт отмечен как сданный.")
            return redirect("platform-regulatory")
        if not user_can(request.user, "M17", "create"):
            return redirect("platform-regulatory")
        form = RegulatorySubmissionForm(request.POST)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.subsystem = m.subsystem
            sub.status = RegulatoryReportSubmission.Status.DRAFT
            sub.save()
            messages.success(request, "Черновик формы сохранён.")
        else:
            messages.error(request, "Проверьте поля формы.")
            return self.render_to_response(self.get_context_data(form=form))
        return redirect("platform-regulatory")


class ChartsView(ModulePermissionMixin, TemplateView):
    module_code = "M18"
    template_name = "platform/analytics/charts.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        days = int(self.request.GET.get("days", 30))
        ctx["analytics_tab"] = "charts"
        ctx["page_title"] = "Графики и визуализация"
        ctx["period_days"] = days
        ctx["charts"] = json.dumps(
            {
                "cases": chart_cases_trend(m.subsystem, days=days),
                "tasks": chart_tasks_by_priority(m.subsystem),
                "corr": chart_correspondence_status(m.subsystem),
            },
            ensure_ascii=False,
        )
        metric = self.request.GET.get("metric", "cases")
        ctx["active_metric"] = metric
        return ctx


class QualityView(ModulePermissionMixin, TemplateView):
    module_code = "M19"
    template_name = "platform/analytics/quality.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "quality"
        ctx["page_title"] = "Оценка качества обработки"
        ctx["metrics"] = quality_metrics(m.subsystem)
        return ctx


class OverdueMonitorView(ModulePermissionMixin, TemplateView):
    module_code = "M20"
    template_name = "platform/analytics/overdue.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "overdue"
        ctx["page_title"] = "Мониторинг просрочек"
        ctx["items"] = overdue_monitor(m.subsystem)
        ctx["counts"] = {
            "red": sum(1 for i in ctx["items"] if i["light"] == "red"),
            "yellow": sum(1 for i in ctx["items"] if i["light"] == "yellow"),
            "green": sum(1 for i in ctx["items"] if i["light"] == "green"),
        }
        return ctx


class DepartmentAnalyticsView(ModulePermissionMixin, TemplateView):
    module_code = "M21"
    template_name = "platform/analytics/departments.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["analytics_tab"] = "departments"
        ctx["page_title"] = "Аналитика по подразделениям"
        org = m.organization
        ctx["rows"] = department_analytics(m.subsystem, org) if org else []
        return ctx
