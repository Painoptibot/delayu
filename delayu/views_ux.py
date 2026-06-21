"""M83–M86 — лицензии, обучение, дашборды, marketplace."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_ux import DashboardLayoutForm, OnboardingArticleForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import MarketplaceConnector, OnboardingArticle, UserDashboardLayout
from delayu.services import ux
from delayu.services.access import user_can
from delayu.views_platform import _ctx_membership


class UxHubView(ModulePermissionMixin, TemplateView):
    module_code = "M83"
    template_name = "platform/ux/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "UX и лицензии"
        ctx["ux_tab"] = "hub"
        ctx["metrics"] = ux.ux_hub_metrics(m.subsystem)
        return ctx


class LicensesView(ModulePermissionMixin, TemplateView):
    module_code = "M83"
    template_name = "platform/ux/licenses.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Лицензирование модулей"
        ctx["ux_tab"] = "licenses"
        ctx["rows"] = ux.license_rows(m.subsystem)
        return ctx


class OnboardingListView(ModulePermissionMixin, TemplateView):
    module_code = "M84"
    template_name = "platform/ux/onboarding.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Обучение и онбординг"
        ctx["ux_tab"] = "onboarding"
        ctx["articles"] = ux.filter_onboarding(m.subsystem, self.request.GET)
        ctx["can_create"] = user_can(self.request.user, "M84", "create")
        return ctx


class OnboardingCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M84"
    required_action = "create"
    template_name = "platform/ux/onboarding_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Материал обучения"
        ctx["ux_tab"] = "onboarding"
        ctx["form"] = kwargs.get("form") or OnboardingArticleForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = OnboardingArticleForm(request.POST)
        if form.is_valid():
            art = form.save(commit=False)
            art.subsystem = m.subsystem
            art.save()
            messages.success(request, "Материал опубликован.")
            return redirect("platform-onboarding")
        return self.render_to_response(self.get_context_data(form=form))


class DashboardLayoutsView(ModulePermissionMixin, TemplateView):
    module_code = "M85"
    template_name = "platform/ux/dashboards.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор дашбордов"
        ctx["ux_tab"] = "dashboards"
        ctx["layouts"] = ux.filter_dashboard_layouts(self.request.user, m.subsystem)
        ctx["can_create"] = user_can(self.request.user, "M85", "create")
        return ctx


class DashboardLayoutCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M85"
    required_action = "create"
    template_name = "platform/ux/dashboard_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Раскладка дашборда"
        ctx["ux_tab"] = "dashboards"
        ctx["form"] = kwargs.get("form") or DashboardLayoutForm()
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = DashboardLayoutForm(request.POST)
        if form.is_valid():
            layout = form.save(commit=False)
            layout.user = request.user
            layout.subsystem = m.subsystem
            if layout.is_default:
                UserDashboardLayout.objects.filter(
                    user=request.user, subsystem=m.subsystem
                ).update(is_default=False)
            layout.save()
            messages.success(request, "Раскладка сохранена.")
            return redirect("platform-dashboard-layouts")
        return self.render_to_response(self.get_context_data(form=form))


class MarketplaceView(ModulePermissionMixin, TemplateView):
    module_code = "M86"
    template_name = "platform/ux/marketplace.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Каталог коннекторов"
        ctx["ux_tab"] = "marketplace"
        ctx["connectors"] = ux.filter_marketplace(self.request.GET)
        return ctx


class MarketplaceInstallView(ModulePermissionMixin, View):
    module_code = "M86"
    required_action = "change"

    def post(self, request, pk):
        conn = get_object_or_404(MarketplaceConnector, pk=pk)
        conn.install_count += 1
        conn.save(update_fields=["install_count"])
        messages.success(request, f"Коннектор «{conn.name}» отмечен как установленный (демо).")
        return redirect("platform-marketplace")
