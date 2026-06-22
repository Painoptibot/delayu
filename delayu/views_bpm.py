"""M33–M36 — BPM, согласования, SLA, регламенты."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from delayu.forms_bpm import (
    BPMStartForm,
    BPMTaskDecisionForm,
    BPMTemplateForm,
    CaseRegulationForm,
    SLARuleForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import BPMInstance, BPMTask, BPMTemplate, CaseFile, CaseRegulation
from delayu.services import audit, bpm
from delayu.services.access import user_can
from delayu.services.regulations import apply_regulation_to_case, filter_regulations
from delayu.services.sla import cases_for_escalation, filter_sla_rules, sla_monitor_metrics
from delayu.services.workplace import log_activity
from delayu.views_platform import _ctx_membership


class BPMTemplatesListView(ModulePermissionMixin, TemplateView):
    module_code = "M33"
    template_name = "platform/bpm/templates.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        from django.db.models import Count

        qs = bpm.filter_templates(m.subsystem, self.request.GET)
        ctx["page_title"] = "Шаблоны процессов"
        ctx["templates"] = qs.annotate(instance_count=Count("bpminstance"))
        ctx["bpm_tab"] = "templates"
        ctx["can_create"] = user_can(self.request.user, "M33", "create")
        ctx["can_change"] = user_can(self.request.user, "M33", "change")
        return ctx


class BPMTemplateWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M33"
    required_action = "create"
    template_name = "platform/bpm/template_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый шаблон BPM"
        ctx["form"] = kwargs.get("form") or BPMTemplateForm()
        ctx["bpm_tab"] = "templates"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = BPMTemplateForm(request.POST)
        if form.is_valid():
            tpl = form.save(commit=False)
            tpl.subsystem = m.subsystem
            tpl.save()
            audit.log_action(
                request.user, m.subsystem, "bpm_template.create", "BPMTemplate", tpl.pk, request=request
            )
            messages.success(request, f"Шаблон «{tpl.name}» создан.")
            return redirect("platform-bpm-templates")
        return self.render_to_response(self.get_context_data(form=form))


class BPMTemplateUpdateView(ModulePermissionMixin, TemplateView):
    module_code = "M33"
    required_action = "change"
    template_name = "platform/bpm/template_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        tpl = get_object_or_404(BPMTemplate, pk=self.kwargs["pk"], subsystem=m.subsystem)
        ctx["page_title"] = f"Редактирование: {tpl.name}"
        ctx["form"] = kwargs.get("form") or BPMTemplateForm(instance=tpl)
        ctx["template_obj"] = tpl
        ctx["bpm_tab"] = "templates"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        tpl = get_object_or_404(BPMTemplate, pk=self.kwargs["pk"], subsystem=m.subsystem)
        form = BPMTemplateForm(request.POST, instance=tpl)
        if form.is_valid():
            form.save()
            messages.success(request, "Шаблон сохранён.")
            return redirect("platform-bpm-templates")
        return self.render_to_response(self.get_context_data(form=form))


class BPMTemplateModalView(ModulePermissionMixin, View):
    module_code = "M33"

    def get(self, request, pk):
        m = _ctx_membership(self)
        tpl = get_object_or_404(BPMTemplate, pk=pk, subsystem=m.subsystem)
        return render(
            request,
            "platform/bpm/_template_modal.html",
            {"tpl": tpl, "can_change": user_can(request.user, "M33", "change")},
        )


class BPMInstancesListView(ModulePermissionMixin, TemplateView):
    module_code = "M33"
    template_name = "platform/bpm/instances.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        qs = bpm.filter_instances(m.subsystem, self.request.GET)
        from django.core.paginator import Paginator

        paginator = Paginator(qs, 25)
        ctx["page_obj"] = paginator.get_page(self.request.GET.get("page", 1))
        ctx["instances"] = ctx["page_obj"]
        ctx["page_title"] = "Экземпляры процессов"
        ctx["bpm_tab"] = "instances"
        ctx["status_choices"] = BPMInstance.Status.choices
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["can_create"] = user_can(self.request.user, "M33", "create")
        return ctx


class BPMInstanceDetailView(ModulePermissionMixin, DetailView):
    module_code = "M33"
    model = BPMInstance
    template_name = "platform/bpm/instance_detail.html"
    context_object_name = "instance"

    def get_queryset(self):
        return BPMInstance.objects.filter(
            template__subsystem=_ctx_membership(self).subsystem
        ).select_related("case", "template")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tasks"] = self.object.tasks.select_related("assignee").order_by("decided_at", "pk")
        ctx["bpm_tab"] = "instances"
        return ctx


class BPMStartView(ModulePermissionMixin, TemplateView):
    module_code = "M33"
    required_action = "create"
    template_name = "platform/bpm/start.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Запуск процесса"
        ctx["form"] = kwargs.get("form") or BPMStartForm(subsystem=m.subsystem)
        ctx["bpm_tab"] = "instances"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = BPMStartForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            inst = bpm.start_process(
                form.cleaned_data["template"],
                form.cleaned_data["case"],
                request.user,
            )
            if inst:
                log_activity(
                    m.subsystem,
                    request.user,
                    "started",
                    inst.template.name,
                    module_code="M33",
                    link_path=reverse("platform-bpm-instance", kwargs={"pk": inst.pk}),
                )
                messages.success(request, "Процесс запущен.")
                return redirect("platform-bpm-instance", pk=inst.pk)
            messages.error(request, "В шаблоне нет шагов.")
        return self.render_to_response(self.get_context_data(form=form))


class BPMApprovalsListView(ModulePermissionMixin, TemplateView):
    module_code = "M34"
    template_name = "platform/bpm/approvals.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        mine = self.request.GET.get("mine", "1") != "0"
        qs = bpm.filter_pending_tasks(
            m.subsystem,
            user=self.request.user if mine else None,
            params=self.request.GET,
        )
        ctx["page_title"] = "Согласования"
        ctx["tasks"] = qs[:50]
        ctx["mine_only"] = mine
        ctx["bpm_tab"] = "approvals"
        return ctx


class BPMTaskDecisionView(ModulePermissionMixin, TemplateView):
    module_code = "M34"
    required_action = "approve"
    template_name = "platform/bpm/task_decision.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        task = get_object_or_404(
            BPMTask,
            pk=self.kwargs["pk"],
            instance__template__subsystem=m.subsystem,
        )
        ctx["task"] = task
        ctx["form"] = BPMTaskDecisionForm()
        ctx["page_title"] = task.step_name
        ctx["bpm_tab"] = "approvals"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        task = get_object_or_404(
            BPMTask,
            pk=self.kwargs["pk"],
            instance__template__subsystem=m.subsystem,
            assignee=request.user,
        )
        approved = request.POST.get("decision") == "approve"
        bpm.advance_process(task, approved, request.POST.get("comment", ""))
        audit.log_action(
            request.user,
            m.subsystem,
            "bpm.decision",
            "BPMTask",
            task.pk,
            {"approved": approved},
            request,
        )
        messages.success(request, "Решение сохранено.")
        return redirect("platform-bpm-approvals")


class CaseBpmDecisionView(ModulePermissionMixin, View):
    """Быстрое решение с карточки дела."""

    module_code = "M34"
    required_action = "approve"

    def post(self, request, pk):
        task = get_object_or_404(BPMTask, pk=pk, assignee=request.user)
        approved = request.POST.get("decision") == "approve"
        bpm.advance_process(task, approved, request.POST.get("comment", ""))
        messages.success(request, "Решение по согласованию сохранено.")
        return redirect("platform-case-detail", pk=task.instance.case_id)


class SLARulesListView(ModulePermissionMixin, TemplateView):
    module_code = "M35"
    template_name = "platform/bpm/sla_rules.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Правила SLA"
        ctx["rules"] = filter_sla_rules(m.subsystem)
        ctx["bpm_tab"] = "sla"
        ctx["can_create"] = user_can(self.request.user, "M35", "create")
        return ctx


class SLARuleWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M35"
    required_action = "create"
    template_name = "platform/bpm/sla_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новое правило SLA"
        ctx["form"] = kwargs.get("form") or SLARuleForm(subsystem=m.subsystem)
        ctx["bpm_tab"] = "sla"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = SLARuleForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.subsystem = m.subsystem
            rule.save()
            messages.success(request, "Правило SLA сохранено.")
            return redirect("platform-bpm-sla")
        return self.render_to_response(self.get_context_data(form=form))


class SLAMonitorView(ModulePermissionMixin, TemplateView):
    module_code = "M35"
    template_name = "platform/bpm/sla_monitor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Мониторинг SLA"
        ctx["metrics"] = sla_monitor_metrics(m.subsystem)
        ctx["escalation_cases"] = cases_for_escalation(m.subsystem)
        ctx["bpm_tab"] = "sla_monitor"
        return ctx


class RegulationsListView(ModulePermissionMixin, TemplateView):
    module_code = "M36"
    template_name = "platform/bpm/regulations.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Регламентные сроки"
        ctx["regulations"] = filter_regulations(m.subsystem)
        ctx["bpm_tab"] = "regulations"
        ctx["can_create"] = user_can(self.request.user, "M36", "create")
        return ctx


class RegulationWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M36"
    required_action = "create"
    template_name = "platform/bpm/regulation_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый регламент"
        ctx["form"] = kwargs.get("form") or CaseRegulationForm()
        ctx["bpm_tab"] = "regulations"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = CaseRegulationForm(request.POST)
        if form.is_valid():
            reg = form.save(commit=False)
            reg.subsystem = m.subsystem
            reg.save()
            messages.success(request, "Регламент сохранён.")
            return redirect("platform-bpm-regulations")
        return self.render_to_response(self.get_context_data(form=form))


class RegulationApplyView(ModulePermissionMixin, View):
    module_code = "M36"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        reg = get_object_or_404(CaseRegulation, pk=pk, subsystem=m.subsystem)
        case_id = request.POST.get("case_id")
        case = get_object_or_404(CaseFile, pk=case_id, subsystem=m.subsystem, is_archived=False)
        if apply_regulation_to_case(case, reg):
            messages.success(request, f"Срок дела установлен: {case.due_date}.")
        else:
            messages.warning(request, "Регламент не применён (не подходит статус дела).")
        return redirect("platform-bpm-regulations")


# Совместимость: главная страница BPM
class BPMListView(BPMInstancesListView):
    pass
