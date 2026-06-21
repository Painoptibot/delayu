"""M73–M77 — НСИ, конструктор форм, массовые операции, выгрузки, поручения."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_operations import (
    BulkOperationForm,
    DirectiveReportForm,
    ExportJobForm,
    FormSchemaForm,
    ManagementDirectiveForm,
    NSIClassifierForm,
    NSIValueForm,
)
from delayu.mixins import CriticalReauthMixin, ModulePermissionMixin
from delayu.models import (
    BulkOperation,
    ExportJob,
    FormSchema,
    ManagementDirective,
    NSIClassifier,
    NSIValue,
)
from delayu.services import nsi, operations
from delayu.services.access import user_can
from delayu.services import audit
from delayu.views_platform import _ctx_membership


class OpsHubView(ModulePermissionMixin, TemplateView):
    module_code = "M73"
    template_name = "platform/ops/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "НСИ и операции"
        ctx["ops_tab"] = "hub"
        ctx["nsi_metrics"] = nsi.nsi_metrics(m.subsystem)
        ctx["metrics"] = operations.ops_hub_metrics(m.subsystem)
        return ctx


class NsiListView(ModulePermissionMixin, TemplateView):
    module_code = "M73"
    template_name = "platform/ops/nsi_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Справочники НСИ"
        ctx["ops_tab"] = "nsi"
        ctx["classifiers"] = nsi.filter_classifiers(m.subsystem, self.request.GET)
        ctx["metrics"] = nsi.nsi_metrics(m.subsystem)
        ctx["can_create"] = user_can(self.request.user, "M73", "create")
        return ctx


class NsiClassifierCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M73"
    required_action = "create"
    template_name = "platform/ops/nsi_classifier_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый справочник"
        ctx["ops_tab"] = "nsi"
        ctx["form"] = kwargs.get("form") or NSIClassifierForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = NSIClassifierForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = m.subsystem
            obj.save()
            messages.success(request, "Справочник создан.")
            return redirect("platform-nsi-detail", pk=obj.pk)
        return self.render_to_response(self.get_context_data(form=form))


class NsiClassifierDetailView(ModulePermissionMixin, TemplateView):
    module_code = "M73"
    template_name = "platform/ops/nsi_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        classifier = get_object_or_404(NSIClassifier, pk=kwargs["pk"], subsystem=m.subsystem)
        ctx["page_title"] = classifier.name
        ctx["ops_tab"] = "nsi"
        ctx["classifier"] = classifier
        ctx["values"] = nsi.filter_values(classifier, self.request.GET)
        ctx["can_create"] = user_can(self.request.user, "M73", "create")
        return ctx


class NsiValueCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M73"
    required_action = "create"
    template_name = "platform/ops/nsi_value_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        classifier = get_object_or_404(NSIClassifier, pk=kwargs["pk"], subsystem=m.subsystem)
        ctx["classifier"] = classifier
        ctx["page_title"] = "Новое значение"
        ctx["ops_tab"] = "nsi"
        ctx["form"] = kwargs.get("form") or NSIValueForm(classifier=classifier)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        classifier = get_object_or_404(NSIClassifier, pk=kwargs["pk"], subsystem=m.subsystem)
        form = NSIValueForm(request.POST, classifier=classifier)
        if form.is_valid():
            val = form.save(commit=False)
            val.classifier = classifier
            val.save()
            messages.success(request, "Значение добавлено.")
            return redirect("platform-nsi-detail", pk=classifier.pk)
        return self.render_to_response(self.get_context_data(form=form))


class CaseKindsListView(ModulePermissionMixin, TemplateView):
    """#21 — типы дел через справочник НСИ case_kind."""

    module_code = "M73"
    template_name = "platform/ops/case_kinds.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        from delayu.models import NSIClassifier

        clf = NSIClassifier.objects.filter(subsystem=m.subsystem, code="case_kind").first()
        ctx["page_title"] = "Типы дел"
        ctx["ops_tab"] = "case_kinds"
        ctx["classifier"] = clf
        ctx["values"] = (
            clf.values.filter(is_active=True).order_by("sort_order", "name") if clf else []
        )
        ctx["can_change"] = user_can(self.request.user, "M73", "change")
        return ctx


class FormSchemasListView(ModulePermissionMixin, TemplateView):
    module_code = "M74"
    template_name = "platform/ops/forms_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор форм"
        ctx["ops_tab"] = "forms"
        ctx["schemas"] = operations.filter_form_schemas(m.subsystem, self.request.GET)
        ctx["can_create"] = user_can(self.request.user, "M74", "create")
        return ctx


class FormSchemaCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M74"
    required_action = "create"
    template_name = "platform/ops/form_schema_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Схема формы"
        ctx["ops_tab"] = "forms"
        ctx["form"] = kwargs.get("form") or FormSchemaForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = FormSchemaForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = m.subsystem
            obj.save()
            from delayu.services.form_schemas import sync_registry_form_schema

            sync_registry_form_schema(obj)
            messages.success(request, "Схема сохранена.")
            return redirect("platform-form-schemas")
        return self.render_to_response(self.get_context_data(form=form))


class FormSchemaEditView(ModulePermissionMixin, TemplateView):
    module_code = "M74"
    required_action = "change"
    template_name = "platform/ops/form_schema_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        schema = get_object_or_404(FormSchema, pk=kwargs["pk"], subsystem=m.subsystem)
        ctx["page_title"] = f"Редактирование: {schema.name or schema.code}"
        ctx["ops_tab"] = "forms"
        ctx["schema"] = schema
        ctx["form"] = kwargs.get("form") or FormSchemaForm(instance=schema)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        schema = get_object_or_404(FormSchema, pk=kwargs["pk"], subsystem=m.subsystem)
        form = FormSchemaForm(request.POST, instance=schema)
        if form.is_valid():
            obj = form.save()
            from delayu.services.form_schemas import sync_registry_form_schema

            sync_registry_form_schema(obj)
            messages.success(request, "Схема обновлена.")
            return redirect("platform-form-schemas")
        return self.render_to_response(self.get_context_data(form=form))


class BulkOperationsView(CriticalReauthMixin, ModulePermissionMixin, TemplateView):
    module_code = "M75"
    template_name = "platform/ops/bulk.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Массовые операции"
        ctx["ops_tab"] = "bulk"
        ctx["form"] = BulkOperationForm(subsystem=m.subsystem)
        ctx["runs"] = operations.filter_bulk_operations(m.subsystem, self.request.GET)[:30]
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = BulkOperationForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            op = form.cleaned_data["operation"]
            filter_params = {}
            payload = {}
            if form.cleaned_data.get("status_filter"):
                filter_params["status"] = form.cleaned_data["status_filter"]
            if op == BulkOperation.Operation.STATUS:
                payload["new_status"] = form.cleaned_data["new_status"]
            elif op == BulkOperation.Operation.ASSIGN:
                assignee = form.cleaned_data.get("assignee")
                if assignee:
                    payload["assignee_id"] = assignee.pk
            run = operations.run_bulk_operation(
                subsystem=m.subsystem,
                user=request.user,
                operation=op,
                filter_params=filter_params,
                payload=payload,
            )
            messages.info(request, run.log)
        return redirect("platform-bulk-ops")


class ExportsListView(ModulePermissionMixin, TemplateView):
    module_code = "M76"
    template_name = "platform/ops/exports.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Реестр выгрузок"
        ctx["ops_tab"] = "exports"
        ctx["form"] = ExportJobForm()
        ctx["jobs"] = operations.filter_export_jobs(m.subsystem, self.request.GET)[:40]
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ExportJobForm(request.POST)
        if form.is_valid():
            operations.create_export_job(
                subsystem=m.subsystem,
                user=request.user,
                kind=form.cleaned_data["kind"],
                title=form.cleaned_data.get("title") or form.cleaned_data["kind"],
                params={},
            )
            messages.success(request, "Выгрузка поставлена в очередь (демо: сразу «Готово»).")
        return redirect("platform-exports")


class DirectivesListView(ModulePermissionMixin, TemplateView):
    module_code = "M77"
    template_name = "platform/ops/directives.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        operations.mark_overdue_directives(m.subsystem)
        ctx["page_title"] = "Поручения руководства"
        ctx["ops_tab"] = "directives"
        ctx["directives"] = operations.filter_directives(m.subsystem, self.request.GET)[:50]
        ctx["can_create"] = user_can(self.request.user, "M77", "create")
        return ctx


class DirectiveCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M77"
    required_action = "create"
    template_name = "platform/ops/directive_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новое поручение"
        ctx["ops_tab"] = "directives"
        ctx["form"] = kwargs.get("form") or ManagementDirectiveForm(subsystem=m.subsystem)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = ManagementDirectiveForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            d = form.save(commit=False)
            d.subsystem = m.subsystem
            d.author = request.user
            d.save()
            audit.log_action(
                request.user, m.subsystem, "create", "ManagementDirective", d.pk, request=request
            )
            messages.success(request, "Поручение зарегистрировано.")
            return redirect("platform-directives")
        return self.render_to_response(self.get_context_data(form=form))


class DirectiveReportView(ModulePermissionMixin, TemplateView):
    module_code = "M77"
    required_action = "change"
    template_name = "platform/ops/directive_report.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["directive"] = get_object_or_404(
            ManagementDirective, pk=kwargs["pk"], subsystem=m.subsystem
        )
        ctx["page_title"] = "Отчёт по поручению"
        ctx["ops_tab"] = "directives"
        ctx["form"] = DirectiveReportForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        directive = get_object_or_404(
            ManagementDirective, pk=kwargs["pk"], subsystem=m.subsystem
        )
        form = DirectiveReportForm(request.POST)
        if form.is_valid():
            directive.report_text = form.cleaned_data["report_text"]
            directive.reported_at = timezone.now()
            directive.status = ManagementDirective.Status.DONE
            directive.save()
            messages.success(request, "Отчёт принят, поручение закрыто.")
            return redirect("platform-directives")
        return self.render_to_response(self.get_context_data(form=form))


class DirectiveModalView(ModulePermissionMixin, View):
    module_code = "M77"

    def get(self, request, pk):
        m = _ctx_membership(self)
        directive = get_object_or_404(ManagementDirective, pk=pk, subsystem=m.subsystem)
        return render(request, "platform/ops/_directive_modal.html", {"directive": directive})


# Alias for menu compatibility
NsiView = NsiListView
