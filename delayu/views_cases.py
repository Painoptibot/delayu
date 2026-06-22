"""M22 — Реестр дел: список, мастер, карточка, popup."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, TemplateView

from delayu.forms_cases import CaseFileForm, CaseWizardForm
from delayu.mixins import CriticalReauthMixin, ModulePermissionMixin
from delayu.models import BPMTask, CaseFile
from delayu.services import ai, audit
from delayu.services.access import user_can
from delayu.services.case_360 import build_case_360_context
from delayu.services.cases import case_card_context, filter_cases, next_case_number
from delayu.services.form_schemas import (
    build_dynamic_form,
    case_extra_context,
    case_schema,
    save_case_extra_data,
)
from delayu.services.workplace import log_activity
from delayu.views_platform import _ctx_membership

User = get_user_model()


class CaseListView(ModulePermissionMixin, TemplateView):
    module_code = "M22"
    template_name = "platform/cases/list.html"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        can_change = user_can(self.request.user, "M22", "change")
        qs = filter_cases(
            m.subsystem,
            self.request.user,
            params=self.request.GET,
            can_change_all=can_change,
        )
        page = self.request.GET.get("page", "1")
        from django.core.paginator import Paginator

        paginator = Paginator(qs, self.paginate_by)
        ctx["page_obj"] = paginator.get_page(page)
        ctx["cases"] = ctx["page_obj"]
        ctx["page_title"] = "Реестр дел"
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        ctx["filter_priority"] = self.request.GET.get("priority", "")
        ctx["filter_overdue"] = self.request.GET.get("overdue", "")
        ctx["status_choices"] = CaseFile.Status.choices
        ctx["assignees"] = User.objects.filter(
            subsystem_memberships__subsystem=m.subsystem
        ).distinct().order_by("username")
        ctx["can_create"] = user_can(self.request.user, "M22", "create")
        ctx["can_change"] = can_change
        ctx["can_bulk"] = user_can(self.request.user, "M22", "bulk") and not ctx.get(
            "demo_mode", False
        )
        return ctx


class CaseBulkView(CriticalReauthMixin, ModulePermissionMixin, View):
    """#33 — массовые операции из реестра дел."""

    module_code = "M22"
    required_action = "bulk"

    def post(self, request):
        m = _ctx_membership(self)
        raw_ids = request.POST.getlist("case_ids")
        try:
            ids = [int(x) for x in raw_ids if str(x).strip()]
        except ValueError:
            messages.error(request, "Некорректный список дел.")
            return redirect("platform-cases")
        if not ids:
            messages.warning(request, "Выберите хотя бы одно дело.")
            return redirect("platform-cases")
        action = request.POST.get("bulk_action", "status")
        status = request.POST.get("new_status", "").strip()
        assignee_raw = request.POST.get("assignee_id", "").strip()
        assignee_id = int(assignee_raw) if assignee_raw.isdigit() else None
        if action == "status" and not status:
            messages.error(request, "Укажите новый статус.")
            return redirect("platform-cases")
        if action == "assign" and not assignee_id:
            messages.error(request, "Укажите исполнителя.")
            return redirect("platform-cases")
        from delayu.services.case_bulk import bulk_update_cases

        run = bulk_update_cases(
            subsystem=m.subsystem,
            user=request.user,
            ids=ids,
            action=action,
            status=status,
            assignee_id=assignee_id,
            request=request,
        )
        messages.success(request, run.log or f"Обработано: {run.affected_count}")
        return redirect("platform-cases")


class CaseModalView(ModulePermissionMixin, View):
    module_code = "M22"

    def get(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(CaseFile, pk=pk, subsystem=m.subsystem)
        ctx = case_card_context(case)
        ctx["can_change"] = user_can(request.user, "M22", "change")
        ctx["ai_summary"] = ai.summarize_case(case)
        ctx["ai_risk"] = ai.risk_overdue(case)
        ctx.update(case_extra_context(case))
        return render(request, "platform/cases/_modal_body.html", ctx)


class CaseDetailView(ModulePermissionMixin, DetailView):
    module_code = "M22"
    model = CaseFile
    template_name = "platform/cases/detail.html"
    context_object_name = "case"

    def get_queryset(self):
        return CaseFile.objects.filter(subsystem=_ctx_membership(self).subsystem)

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        from delayu.services.case_acl import user_can_view_case

        if not user_can_view_case(self.request.user, obj):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Нет доступа к этому делу")
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["documents"] = self.object.documents.filter(is_current=True).order_by("-version")
        ctx["comments"] = self.object.comments.filter(parent__isnull=True).select_related(
            "author"
        ).prefetch_related("replies", "replies__author")
        ctx["bpm_tasks"] = BPMTask.objects.filter(
            instance__case=self.object, status=BPMTask.Status.PENDING
        )
        ctx["my_bpm_tasks"] = BPMTask.objects.filter(
            instance__case=self.object,
            status=BPMTask.Status.PENDING,
            assignee=self.request.user,
        )
        ctx["ai_summary"] = ai.summarize_case(self.object)
        ctx["ai_risk"] = ai.risk_overdue(self.object)
        ctx["can_m06_change"] = user_can(self.request.user, "M06", "change")
        ctx["can_archive"] = user_can(self.request.user, "M06", "archive")
        ctx["can_change"] = user_can(self.request.user, "M22", "change")
        ctx["status_choices"] = CaseFile.Status.choices
        ctx["active_tab"] = self.request.GET.get("tab", "overview")
        ctx.update(build_case_360_context(self.object))
        ctx.update(case_extra_context(self.object))
        return ctx


class CaseWizardCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M22"
    required_action = "create"
    template_name = "platform/cases/wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новое дело"
        schema = case_schema(m.subsystem)
        ctx["form"] = kwargs.get("form") or CaseWizardForm(subsystem=m.subsystem)
        ctx["extra_form"] = kwargs.get("extra_form") or (
            build_dynamic_form(schema, prefix="extra_") if schema else None
        )
        ctx["form_schema"] = schema
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        schema = case_schema(m.subsystem)
        form = CaseWizardForm(request.POST, subsystem=m.subsystem)
        extra_form = (
            build_dynamic_form(schema, data=request.POST, prefix="extra_") if schema else None
        )
        extra_ok = extra_form.is_valid() if extra_form else True
        if form.is_valid() and extra_ok:
            case = CaseFile.objects.create(
                subsystem=m.subsystem,
                organization=m.organization,
                number=next_case_number(m.subsystem),
                created_by=request.user,
                title=form.cleaned_data["title"],
                description=form.cleaned_data.get("description", ""),
                assignee=form.cleaned_data.get("assignee"),
                due_date=form.cleaned_data.get("due_date"),
                priority=form.cleaned_data["priority"],
                status=form.cleaned_data["status"],
                extra_data={},
            )
            if extra_form and schema:
                save_case_extra_data(case, extra_form, schema, prefix="extra_")
            audit.log_action(
                request.user, m.subsystem, "create", "CaseFile", case.pk, request=request
            )
            log_activity(
                m.subsystem,
                request.user,
                "создал дело",
                case.number,
                module_code="M22",
                link_path=reverse("platform-case-detail", kwargs={"pk": case.pk}),
            )
            messages.success(request, f"Дело {case.number} создано.")
            return redirect(f"{reverse('platform-cases')}?open={case.pk}")
        return self.render_to_response(
            self.get_context_data(form=form, extra_form=extra_form)
        )


class CaseUpdateView(ModulePermissionMixin, TemplateView):
    module_code = "M22"
    required_action = "change"
    template_name = "platform/cases/form.html"

    def get_object(self):
        return get_object_or_404(
            CaseFile,
            pk=self.kwargs["pk"],
            subsystem=_ctx_membership(self).subsystem,
            is_archived=False,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        case = kwargs.get("case") or self.get_object()
        m = _ctx_membership(self)
        ctx["object"] = case
        ctx["page_title"] = f"Дело {case.number}"
        schema = case_schema(m.subsystem)
        ctx["form"] = kwargs.get("form") or CaseFileForm(
            instance=case, subsystem=m.subsystem
        )
        ctx["extra_form"] = kwargs.get("extra_form") or (
            build_dynamic_form(schema, initial=case.extra_data or {}, prefix="extra_")
            if schema
            else None
        )
        ctx["form_schema"] = schema
        return ctx

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self.get_context_data())

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        case = self.get_object()
        schema = case_schema(m.subsystem)
        form = CaseFileForm(request.POST, instance=case, subsystem=m.subsystem)
        extra_form = (
            build_dynamic_form(
                schema, data=request.POST, initial=case.extra_data or {}, prefix="extra_"
            )
            if schema
            else None
        )
        extra_ok = extra_form.is_valid() if extra_form else True
        if form.is_valid() and extra_ok:
            case = form.save()
            if extra_form and schema:
                save_case_extra_data(case, extra_form, schema, prefix="extra_")
            audit.log_action(
                request.user, m.subsystem, "update", "CaseFile", case.pk, request=request
            )
            messages.success(request, "Дело сохранено.")
            return redirect("platform-case-detail", pk=case.pk)
        return self.render_to_response(
            self.get_context_data(form=form, extra_form=extra_form, case=case)
        )


class CaseStatusView(ModulePermissionMixin, View):
    module_code = "M22"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(
            CaseFile, pk=pk, subsystem=m.subsystem, is_archived=False
        )
        status = request.POST.get("status")
        if status in dict(CaseFile.Status.choices):
            case.status = status
            case.save(update_fields=["status", "updated_at"])
            messages.success(request, "Статус обновлён.")
        return redirect("platform-case-detail", pk=pk)
