"""M83–M86 — лицензии, обучение, дашборды, marketplace."""
from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_ux import CustomerLicenseForm, DashboardLayoutForm, OnboardingArticleForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import CustomerLicense, MarketplaceConnector, OnboardingArticle, UserDashboardLayout
from delayu.services import licenses as license_svc
from delayu.services import ux
from delayu.services.licenses import LicenseError
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
        ctx["page_title"] = "Лицензии"
        ctx["ux_tab"] = "licenses"
        ctx["rows"] = ux.license_rows(m.subsystem)
        issued = (
            CustomerLicense.objects.filter(subsystem=m.subsystem)
            .select_related("organization", "subsystem")
            .prefetch_related("modules")
            .annotate(used=Count("seat_assignments"))
        )
        ctx["issued"] = [
            {
                "license": lic,
                "used": lic.used,
                "usable": license_svc.license_is_usable(lic),
                "visual": license_svc.license_visual(lic, lic.used),
            }
            for lic in issued
        ]
        ctx["can_create"] = user_can(self.request.user, "M83", "create")
        from delayu.models import ProductRelease

        ctx["releases"] = ProductRelease.objects.all()[:12]
        ctx["can_change"] = user_can(self.request.user, "M83", "change")
        return ctx

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") != "release":
            return redirect("platform-licenses")
        if not user_can(request.user, "M83", "change"):
            messages.error(request, "Нет права регистрировать выпуски.")
            return redirect("platform-licenses")
        from datetime import date

        from delayu.models import ProductRelease

        version = (request.POST.get("version") or "").strip()
        title = (request.POST.get("title") or "").strip()
        released = (request.POST.get("released_on") or "").strip()
        if not version or not title or not released:
            messages.error(request, "Укажите версию, название и дату выпуска.")
            return redirect("platform-licenses")
        try:
            released_on = date.fromisoformat(released)
        except ValueError:
            messages.error(request, "Дата выпуска указана неверно.")
            return redirect("platform-licenses")
        ProductRelease.objects.update_or_create(
            version=version,
            defaults={"title": title, "body": request.POST.get("body") or "", "released_on": released_on},
        )
        messages.success(request, f"Выпуск {version} зарегистрирован.")
        return redirect("platform-licenses")


class CustomerLicenseCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M83"
    required_action = "create"
    template_name = "platform/ux/license_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Выдать лицензию"
        ctx["ux_tab"] = "licenses"
        ctx["form"] = kwargs.get("form") or CustomerLicenseForm(subsystem=m.subsystem)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = CustomerLicenseForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            data = form.cleaned_data
            try:
                lic = license_svc.issue_license(
                    subsystem=m.subsystem,
                    organization=data["organization"],
                    title=data.get("title") or "",
                    seats=data["seats"],
                    valid_from=data["valid_from"],
                    valid_until=data.get("valid_until"),
                    support_until=data.get("support_until"),
                    note=data.get("note") or "",
                    modules=data.get("modules"),
                    issued_by=request.user,
                )
            except LicenseError as exc:
                messages.error(request, str(exc))
                return self.render_to_response(self.get_context_data(form=form))
            messages.success(request, f"Лицензия {lic.number} выдана заказчику {lic.organization}.")
            return redirect("platform-license-detail", pk=lic.pk)
        return self.render_to_response(self.get_context_data(form=form))


class CustomerLicenseDetailView(ModulePermissionMixin, TemplateView):
    module_code = "M83"
    template_name = "platform/ux/license_detail.html"

    def _license(self):
        m = _ctx_membership(self)
        return get_object_or_404(
            CustomerLicense.objects.select_related("organization", "subsystem").prefetch_related(
                "modules"
            ),
            pk=self.kwargs["pk"],
            subsystem=m.subsystem,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        lic = self._license()
        ctx["page_title"] = lic.number
        ctx["ux_tab"] = "licenses"
        ctx["license"] = lic
        ctx["seats"] = lic.seat_assignments.select_related("user", "assigned_by")
        ctx["used"] = ctx["seats"].count()
        ctx["usable"] = license_svc.license_is_usable(lic)
        ctx["free"] = max(lic.seats - ctx["used"], 0)
        ctx["candidates"] = license_svc.assignable_users(lic)
        ctx["can_change"] = user_can(self.request.user, "M83", "change")
        ctx["status_choices"] = CustomerLicense.Status.choices
        ctx["visual"] = license_svc.license_visual(lic, ctx["used"])
        from delayu.models import ProductRelease

        releases = ProductRelease.objects.all()
        if lic.support_until:
            releases = releases.filter(released_on__lte=lic.support_until)
        ctx["releases"] = releases[:12]
        ctx["installed_version"] = lic.subsystem.config_version
        ctx["tickets"] = lic.support_tickets.all()[:20]
        return ctx

    def post(self, request, *args, **kwargs):
        if not user_can(request.user, "M83", "change"):
            messages.error(request, "Нет права изменять лицензии.")
            return redirect("platform-license-detail", pk=kwargs["pk"])
        lic = self._license()
        action = request.POST.get("action")
        try:
            if action == "assign":
                from django.contrib.auth import get_user_model

                user = get_user_model().objects.filter(pk=request.POST.get("user_id")).first()
                if not user:
                    raise LicenseError("Пользователь не выбран.")
                license_svc.assign_seat(lic, user, request.user)
                messages.success(request, "Место выдано.")
            elif action == "release":
                license_svc.release_seat(lic, request.POST.get("seat_id"))
                messages.success(request, "Место освобождено.")
            elif action == "status":
                status = request.POST.get("status")
                allowed = {choice for choice, _label in CustomerLicense.Status.choices}
                if status not in allowed:
                    raise LicenseError("Неизвестный статус.")
                lic.status = status
                lic.save(update_fields=["status"])
                messages.success(request, "Статус лицензии обновлён.")
            elif action == "ticket":
                title = (request.POST.get("title") or "").strip()
                if not title:
                    raise LicenseError("Укажите тему обращения.")
                from delayu.models import LicenseSupportTicket

                number = "SL-" + __import__("secrets").token_hex(3).upper()
                LicenseSupportTicket.objects.create(
                    license=lic,
                    number=number,
                    title=title,
                    body=request.POST.get("body") or "",
                    author=request.user,
                )
                messages.success(request, f"Обращение {number} зарегистрировано.")
            elif action == "ticket_status":
                from delayu.models import LicenseSupportTicket

                ticket = lic.support_tickets.filter(pk=request.POST.get("ticket_id")).first()
                status = request.POST.get("ticket_status")
                allowed = {choice for choice, _label in LicenseSupportTicket.Status.choices}
                if not ticket or status not in allowed:
                    raise LicenseError("Обращение не найдено.")
                ticket.status = status
                ticket.save(update_fields=["status"])
                messages.success(request, "Статус обращения обновлён.")
            elif action == "adopt":
                from delayu.models import ProductRelease

                release = ProductRelease.objects.filter(pk=request.POST.get("release_id")).first()
                if not release:
                    raise LicenseError("Выпуск не найден.")
                if lic.support_until and release.released_on > lic.support_until:
                    raise LicenseError("Поддержка лицензии этот выпуск не покрывает.")
                lic.subsystem.config_version = release.version
                lic.subsystem.save(update_fields=["config_version"])
                messages.success(request, f"Контур отмечен версией {release.version}.")
            else:
                raise LicenseError("Неизвестное действие.")
        except LicenseError as exc:
            messages.error(request, str(exc))
        return redirect("platform-license-detail", pk=lic.pk)


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
