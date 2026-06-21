"""M67–M72 — инфраструктура: GIS, PWA, SSO, ETL, Data Hub, портал гражданина."""
import json

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_infra import (
    CitizenAppealForm,
    DataDatasetForm,
    EtlJobForm,
    GeoLayerForm,
    GeoObjectForm,
    SsoProviderForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models import CitizenAppeal, DataDataset, EtlJob, EtlRun, GeoLayer, PwaDraft
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services import infra
from delayu.views_platform import _ctx_membership


class InfraHubView(ModulePermissionMixin, TemplateView):
    module_code = "M67"
    template_name = "platform/infra/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Инфраструктура"
        ctx["infra_tab"] = "hub"
        ctx["metrics"] = infra.infra_hub_metrics(m.subsystem)
        return ctx


class GisMapView(ModulePermissionMixin, TemplateView):
    module_code = "M67"
    template_name = "platform/infra/gis.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Геопортал"
        ctx["infra_tab"] = "gis"
        ctx["layers"] = infra.filter_geo_layers(m.subsystem, self.request.GET)
        ctx["objects"] = infra.filter_geo_objects(m.subsystem, self.request.GET)[:50]
        ctx["map_points_json"] = json.dumps(infra.geo_objects_for_map(m.subsystem))
        ctx["can_create"] = user_can(self.request.user, "M67", "create")
        return ctx


class GeoLayerCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M67"
    required_action = "create"
    template_name = "platform/infra/geo_layer_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Новый слой"
        ctx["form"] = kwargs.get("form") or GeoLayerForm()
        ctx["infra_tab"] = "gis"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = GeoLayerForm(request.POST)
        if form.is_valid():
            layer = form.save(commit=False)
            layer.subsystem = m.subsystem
            layer.save()
            audit.log_action(
                request.user, m.subsystem, "create", "GeoLayer", layer.pk, request=request
            )
            messages.success(request, "Слой создан.")
            return redirect("platform-gis")
        return self.render_to_response(self.get_context_data(form=form))


class GeoObjectCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M67"
    required_action = "create"
    template_name = "platform/infra/geo_object_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новый объект"
        ctx["form"] = kwargs.get("form") or GeoObjectForm(subsystem=m.subsystem)
        ctx["infra_tab"] = "gis"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = GeoObjectForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = m.subsystem
            obj.save()
            audit.log_action(
                request.user, m.subsystem, "create", "GeoObject", obj.pk, request=request
            )
            messages.success(request, "Объект добавлен на карту.")
            return redirect("platform-gis")
        return self.render_to_response(self.get_context_data(form=form))


class PwaHubView(ModulePermissionMixin, TemplateView):
    module_code = "M68"
    template_name = "platform/infra/pwa.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Мобильное PWA"
        ctx["infra_tab"] = "pwa"
        ctx["devices"] = infra.filter_pwa_devices(m.subsystem, self.request.GET)
        ctx["drafts"] = infra.filter_pwa_drafts(m.subsystem, pending_only=True)[:20]
        return ctx


class PwaDraftSyncView(ModulePermissionMixin, View):
    module_code = "M68"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        draft = get_object_or_404(PwaDraft, pk=pk, device__subsystem=m.subsystem)
        infra.sync_pwa_draft(draft)
        messages.success(request, "Черновик синхронизирован.")
        return redirect("platform-pwa")


class SsoProvidersView(ModulePermissionMixin, TemplateView):
    module_code = "M69"
    template_name = "platform/infra/sso.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "SSO / ЕСИА"
        ctx["infra_tab"] = "sso"
        ctx["providers"] = infra.filter_sso_providers(m.subsystem, self.request.GET)
        ctx["can_create"] = user_can(self.request.user, "M69", "create")
        return ctx


class SsoProviderCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M69"
    required_action = "create"
    template_name = "platform/infra/sso_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Провайдер SSO"
        ctx["form"] = kwargs.get("form") or SsoProviderForm()
        ctx["infra_tab"] = "sso"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = SsoProviderForm(request.POST)
        if form.is_valid():
            prov = form.save(commit=False)
            prov.subsystem = m.subsystem
            prov.save()
            messages.success(request, "Провайдер сохранён.")
            return redirect("platform-sso")
        return self.render_to_response(self.get_context_data(form=form))


class EtlHubView(ModulePermissionMixin, TemplateView):
    module_code = "M70"
    template_name = "platform/infra/etl.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "ETL и импорт"
        ctx["infra_tab"] = "etl"
        ctx["jobs"] = infra.filter_etl_jobs(m.subsystem, self.request.GET)
        ctx["runs"] = infra.filter_etl_runs(m.subsystem, self.request.GET)[:25]
        ctx["failed_runs"] = infra.filter_etl_runs(m.subsystem, {"status": "failed"})[:5]
        ctx["can_create"] = user_can(self.request.user, "M70", "create")
        return ctx


class EtlJobCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M70"
    required_action = "create"
    template_name = "platform/infra/etl_job_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Задание ETL"
        ctx["form"] = kwargs.get("form") or EtlJobForm()
        ctx["infra_tab"] = "etl"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = EtlJobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.subsystem = m.subsystem
            job.save()
            messages.success(request, "Задание ETL создано.")
            return redirect("platform-etl")
        return self.render_to_response(self.get_context_data(form=form))


class EtlRunStartView(ModulePermissionMixin, View):
    module_code = "M70"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        job = get_object_or_404(EtlJob, pk=pk, subsystem=m.subsystem)
        run = infra.run_etl_job(job)
        messages.info(request, f"Запуск #{run.pk}: {run.get_status_display()} — {run.log}")
        return redirect("platform-etl")


class DataHubView(ModulePermissionMixin, TemplateView):
    module_code = "M71"
    template_name = "platform/infra/data_hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Витрина данных"
        ctx["infra_tab"] = "data"
        ctx["datasets"] = infra.filter_datasets(m.subsystem, self.request.GET)
        ctx["can_create"] = user_can(self.request.user, "M71", "create")
        return ctx


class DataDatasetCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M71"
    required_action = "create"
    template_name = "platform/infra/dataset_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Набор данных"
        ctx["form"] = kwargs.get("form") or DataDatasetForm()
        ctx["infra_tab"] = "data"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = DataDatasetForm(request.POST)
        if form.is_valid():
            ds = form.save(commit=False)
            ds.subsystem = m.subsystem
            ds.save()
            messages.success(request, "Набор опубликован в каталоге.")
            return redirect("platform-data-hub")
        return self.render_to_response(self.get_context_data(form=form))


class CitizenPortalView(ModulePermissionMixin, TemplateView):
    module_code = "M72"
    template_name = "platform/infra/citizen.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Портал гражданина"
        ctx["infra_tab"] = "citizen"
        ctx["appeals"] = infra.filter_citizen_appeals(m.subsystem, self.request.GET)[:50]
        ctx["can_create"] = user_can(self.request.user, "M72", "create")
        if m.subsystem.industry_template == "uzhv":
            from django.urls import reverse

            ctx["uzhv_public_appeal_url"] = reverse(
                "uzhv-public-appeal", args=[m.subsystem.code]
            )
        return ctx


class CitizenAppealCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M72"
    required_action = "create"
    template_name = "platform/infra/citizen_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Обращение"
        ctx["form"] = kwargs.get("form") or CitizenAppealForm(subsystem=m.subsystem)
        ctx["infra_tab"] = "citizen"
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = CitizenAppealForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            appeal = form.save(commit=False)
            appeal.subsystem = m.subsystem
            appeal.save()
            messages.success(request, "Обращение зарегистрировано.")
            return redirect("platform-citizen")
        return self.render_to_response(self.get_context_data(form=form))


class CitizenAppealModalView(ModulePermissionMixin, View):
    module_code = "M72"

    def get(self, request, pk):
        m = _ctx_membership(self)
        appeal = get_object_or_404(CitizenAppeal, pk=pk, subsystem=m.subsystem)
        return render(request, "platform/infra/_citizen_modal.html", {"appeal": appeal})
