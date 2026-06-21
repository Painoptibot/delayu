"""M23 — Универсальные реестры: типы, записи, импорт."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_registries import RegistryImportForm, RegistryTypeForm, build_record_form
from delayu.mixins import ModulePermissionMixin
from delayu.models import RegistryRecord, RegistryType
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.form_schemas import resolve_registry_schema
from delayu.services.registries import import_records, validate_record_data
from delayu.views_platform import _ctx_membership


class RegistriesListView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    template_name = "platform/registry/types.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Универсальные реестры"
        qs = RegistryType.objects.filter(subsystem=m.subsystem)
        if self.request.GET.get("active") == "1":
            qs = qs.filter(is_active=True)
        from django.db.models import Count

        ctx["types"] = qs.annotate(record_count=Count("records"))
        ctx["can_create"] = user_can(self.request.user, "M23", "create")
        ctx["can_change"] = user_can(self.request.user, "M23", "change")
        return ctx


class RegistryTypeWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    required_action = "create"
    template_name = "platform/registry/type_wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый тип реестра"
        ctx["form"] = kwargs.get("form") or RegistryTypeForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = RegistryTypeForm(request.POST)
        if form.is_valid():
            rt = form.save(commit=False)
            rt.subsystem = m.subsystem
            rt.save()
            audit.log_action(
                request.user, m.subsystem, "registry_type.create", "RegistryType", rt.pk, request=request
            )
            messages.success(request, f"Тип реестра «{rt.name}» создан.")
            return redirect("platform-registry-records", type_pk=rt.pk)
        return self.render_to_response(self.get_context_data(form=form))


class RegistryTypeModalView(ModulePermissionMixin, View):
    module_code = "M23"

    def get(self, request, pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=pk, subsystem=m.subsystem)
        return render(
            request,
            "platform/registry/_type_modal.html",
            {
                "registry_type": rt,
                "can_change": user_can(request.user, "M23", "change"),
            },
        )


class RegistryTypeUpdateView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    required_action = "change"
    template_name = "platform/registry/type_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=self.kwargs["pk"], subsystem=m.subsystem)
        ctx["registry_type"] = rt
        ctx["page_title"] = f"Тип: {rt.name}"
        ctx["form"] = kwargs.get("form") or RegistryTypeForm(instance=rt)
        return ctx

    def post(self, request, pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=pk, subsystem=m.subsystem)
        form = RegistryTypeForm(request.POST, instance=rt)
        if form.is_valid():
            form.save()
            messages.success(request, "Тип реестра сохранён.")
            return redirect("platform-registries")
        return self.render_to_response(self.get_context_data(form=form, registry_type=rt))


class RegistryRecordsView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    template_name = "platform/registry/records.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        self.registry_type = get_object_or_404(
            RegistryType, pk=self.kwargs["type_pk"], subsystem=m.subsystem
        )
        ctx["registry_type"] = self.registry_type
        ctx["page_title"] = self.registry_type.name
        qs = RegistryRecord.objects.filter(registry_type=self.registry_type).select_related(
            "created_by"
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(data__icontains=q)
        schema = resolve_registry_schema(self.registry_type)
        records = list(qs[:200])
        for rec in records:
            rec.row_cells = [rec.data.get(f.get("key"), "") for f in schema]
        ctx["records"] = records
        ctx["schema"] = schema
        ctx["search_q"] = q
        ctx["can_create"] = user_can(self.request.user, "M23", "create")
        ctx["can_change"] = user_can(self.request.user, "M23", "change")
        ctx["can_delete"] = user_can(self.request.user, "M23", "delete")
        return ctx


class RegistryRecordFormModalView(ModulePermissionMixin, View):
    """Создание / редактирование записи реестра в модальном окне."""

    module_code = "M23"

    def _rt(self, type_pk):
        m = _ctx_membership(self)
        return get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem), m

    def _form_action(self, type_pk, pk=None):
        if pk:
            return reverse(
                "platform-registry-record-form-modal-edit",
                kwargs={"type_pk": type_pk, "pk": pk},
            )
        return reverse("platform-registry-record-form-modal", kwargs={"type_pk": type_pk})

    def get(self, request, type_pk, pk=None):
        pk = pk or self.kwargs.get("pk")
        rt, m = self._rt(type_pk)
        if pk:
            if not user_can(request.user, "M23", "change"):
                return JsonResponse({"error": "forbidden"}, status=403)
            rec = get_object_or_404(RegistryRecord, pk=pk, registry_type=rt)
            initial = {k: rec.data.get(k, "") for k in rec.data}
            form = build_record_form(rt, initial=initial)
            title = f"Запись #{rec.pk}"
        else:
            if not user_can(request.user, "M23", "create"):
                return JsonResponse({"error": "forbidden"}, status=403)
            form = build_record_form(rt)
            title = "Новая запись"
        action = self._form_action(type_pk, pk)
        return render(
            request,
            "platform/registry/_record_form_modal.html",
            {
                "registry_type": rt,
                "record": pk,
                "form": form,
                "form_action": action,
                "modal_title": title,
            },
        )

    def post(self, request, type_pk, pk=None):
        pk = pk or self.kwargs.get("pk")
        rt, m = self._rt(type_pk)
        form = build_record_form(rt, request.POST)
        if not form.is_valid():
            action = self._form_action(type_pk, pk)
            return render(
                request,
                "platform/registry/_record_form_modal.html",
                {
                    "registry_type": rt,
                    "form": form,
                    "form_action": action,
                    "modal_title": "Проверьте поля",
                },
                status=400,
            )
        cleaned, errors = validate_record_data(rt, form.cleaned_data)
        if errors:
            for msg in errors.values():
                messages.error(request, msg)
            action = self._form_action(type_pk, pk)
            return render(
                request,
                "platform/registry/_record_form_modal.html",
                {
                    "registry_type": rt,
                    "form": form,
                    "form_action": action,
                    "modal_title": "Проверьте поля",
                },
                status=400,
            )
        if pk:
            if not user_can(request.user, "M23", "change"):
                return JsonResponse({"error": "forbidden"}, status=403)
            rec = get_object_or_404(RegistryRecord, pk=pk, registry_type=rt)
            rec.data = cleaned
            rec.save(update_fields=["data"])
        else:
            if not user_can(request.user, "M23", "create"):
                return JsonResponse({"error": "forbidden"}, status=403)
            RegistryRecord.objects.create(
                registry_type=rt,
                organization=m.organization,
                data=cleaned,
                created_by=request.user,
            )
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        return redirect("platform-registry-records", type_pk=rt.pk)


class RegistryRecordModalView(ModulePermissionMixin, View):
    module_code = "M23"

    def get(self, request, type_pk, pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem)
        rec = get_object_or_404(RegistryRecord, pk=pk, registry_type=rt)
        fields_display = [
            (f.get("label", f["key"]), rec.data.get(f["key"], ""))
            for f in resolve_registry_schema(rt)
        ]
        return render(
            request,
            "platform/registry/_record_modal.html",
            {
                "registry_type": rt,
                "record": rec,
                "fields_display": fields_display,
                "can_change": user_can(request.user, "M23", "change"),
            },
        )


class RegistryRecordCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    required_action = "create"
    template_name = "platform/registry/record_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=self.kwargs["type_pk"], subsystem=m.subsystem)
        ctx["registry_type"] = rt
        ctx["page_title"] = f"Новая запись — {rt.name}"
        ctx["form"] = kwargs.get("form") or build_record_form(rt)
        return ctx

    def post(self, request, type_pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem)
        form = build_record_form(rt, request.POST)
        if form.is_valid():
            cleaned, errors = validate_record_data(rt, form.cleaned_data)
            if errors:
                for msg in errors.values():
                    messages.error(request, msg)
                return self.render_to_response(self.get_context_data(form=form, registry_type=rt))
            RegistryRecord.objects.create(
                registry_type=rt,
                organization=m.organization,
                data=cleaned,
                created_by=request.user,
            )
            messages.success(request, "Запись добавлена.")
            return redirect("platform-registry-records", type_pk=rt.pk)
        return self.render_to_response(self.get_context_data(form=form, registry_type=rt))


class RegistryRecordUpdateView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    required_action = "change"
    template_name = "platform/registry/record_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=self.kwargs["type_pk"], subsystem=m.subsystem)
        rec = get_object_or_404(RegistryRecord, pk=self.kwargs["pk"], registry_type=rt)
        ctx["registry_type"] = rt
        ctx["record"] = rec
        ctx["page_title"] = f"Запись #{rec.pk}"
        initial = {k: rec.data.get(k, "") for k in rec.data}
        ctx["form"] = kwargs.get("form") or build_record_form(rt, initial=initial)
        return ctx

    def post(self, request, type_pk, pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem)
        rec = get_object_or_404(RegistryRecord, pk=pk, registry_type=rt)
        form = build_record_form(rt, request.POST)
        if form.is_valid():
            cleaned, errors = validate_record_data(rt, form.cleaned_data)
            if errors:
                for msg in errors.values():
                    messages.error(request, msg)
                return self.render_to_response(
                    self.get_context_data(form=form, registry_type=rt, record=rec)
                )
            rec.data = cleaned
            rec.save(update_fields=["data"])
            messages.success(request, "Запись сохранена.")
            return redirect("platform-registry-records", type_pk=rt.pk)
        return self.render_to_response(
            self.get_context_data(form=form, registry_type=rt, record=rec)
        )


class RegistryRecordDeleteView(ModulePermissionMixin, View):
    module_code = "M23"
    required_action = "delete"

    def post(self, request, type_pk, pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem)
        rec = get_object_or_404(RegistryRecord, pk=pk, registry_type=rt)
        rec.delete()
        messages.success(request, "Запись удалена.")
        return redirect("platform-registry-records", type_pk=rt.pk)


class RegistryImportView(ModulePermissionMixin, TemplateView):
    module_code = "M23"
    required_action = "create"
    template_name = "platform/registry/import.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=self.kwargs["type_pk"], subsystem=m.subsystem)
        ctx["registry_type"] = rt
        ctx["page_title"] = f"Импорт — {rt.name}"
        ctx["form"] = RegistryImportForm()
        return ctx

    def post(self, request, type_pk):
        m = _ctx_membership(self)
        rt = get_object_or_404(RegistryType, pk=type_pk, subsystem=m.subsystem)
        form = RegistryImportForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form, registry_type=rt))
        try:
            rows = json.loads(form.cleaned_data["payload"])
            if not isinstance(rows, list):
                raise ValueError("Ожидается JSON-массив")
        except (json.JSONDecodeError, ValueError) as exc:
            messages.error(request, str(exc))
            return self.render_to_response(self.get_context_data(form=form, registry_type=rt))
        created, errors = import_records(rt, m.organization, request.user, rows)
        if created:
            messages.success(request, f"Импортировано записей: {created}.")
        for err in errors[:5]:
            messages.warning(request, err)
        return redirect("platform-registry-records", type_pk=rt.pk)
