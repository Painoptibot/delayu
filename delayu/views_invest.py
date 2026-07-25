"""Views for the invest subsystem."""

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from delayu.forms_invest import InvestProjectForm, InvestSiteForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import Subsystem
from delayu.models_invest import (
    InvestHandoff,
    InvestImportBatch,
    InvestImportRow,
    InvestPackageItem,
    InvestProject,
    InvestSite,
    InvestSmevRequest,
)
from delayu.services.access import get_membership_or_403, user_can
from delayu.services.invest_booking import InvestBookingError, book_site, select_site
from delayu.services.invest_dashboard import build_dashboard
from delayu.services.invest_handoff import (
    InvestHandoffError,
    accept_handoff,
    request_handoff,
    return_handoff,
)
from delayu.services.invest_import import apply_row, parse_mo_file, skip_row
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.services.invest_scope import projects_for_membership, sites_for_membership
from delayu.services.invest_smev import InvestSmevError, apply_smev_response, request_smev_fill


class InvestSubsystemMixin(AccessMixin):
    module_code = "M22"
    page_title = "Инвестконтур"

    def get_membership(self):
        if not hasattr(self, "_invest_membership"):
            self._invest_membership = get_membership_or_403(self.request)
        return self._invest_membership

    def get_subsystem(self):
        return self.get_membership().subsystem

    def dispatch(self, request, *args, **kwargs):
        # До ModulePermissionMixin: иначе AnonymousUser уходит в filter(user=…).
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
        return super().dispatch(request, *args, **kwargs)


class InvestForbiddenResponseMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not user_can(
            request.user, self.module_code, self.required_action
        ):
            return HttpResponseForbidden(f"Нет доступа к {self.module_code}")
        return super().dispatch(request, *args, **kwargs)


class InvestImportRoleMixin:
    allowed_role_codes = {"invest_mo", "invest_dept", "invest_admin"}

    def dispatch(self, request, *args, **kwargs):
        membership = get_membership_or_403(request)
        if membership.role.code not in self.allowed_role_codes:
            return HttpResponseForbidden("Импорт доступен только ролям МО, департамента и администратора")
        return super().dispatch(request, *args, **kwargs)


def _import_batches_for_membership(membership):
    qs = InvestImportBatch.objects.filter(subsystem=membership.subsystem).select_related("organization")
    if membership.role.code == "invest_mo":
        qs = qs.filter(organization=membership.organization)
    return qs


def _membership_has_role(membership, allowed_role_codes):
    return membership.role.code in allowed_role_codes


def _forbidden_with_message(request, message):
    messages.error(request, message)
    return HttpResponseForbidden(message)


class InvestHubView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/hub.html"
    page_title = "Обзор инвестконтура"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        projects = projects_for_membership(self.get_membership())
        ctx["stats"] = {
            "projects_total": projects.count(),
            "attraction": projects.filter(funnel=InvestProject.Funnel.ATTRACTION).count(),
            "support": projects.filter(funnel=InvestProject.Funnel.SUPPORT).count(),
        }
        ctx["recent_projects"] = projects.select_related("organization", "owner")[:8]
        ctx["can_create_project"] = user_can(self.request.user, self.module_code, "create")
        return ctx


class InvestDashboardView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/dashboard.html"
    page_title = "Дашборд руководителя"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["dashboard"] = build_dashboard(self.get_subsystem())
        return ctx


class InvestProjectListView(InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestProject
    template_name = "invest/projects_list.html"
    context_object_name = "projects"
    page_title = "Инвестпроекты"
    paginate_by = 25

    def get_queryset(self):
        return projects_for_membership(self.get_membership()).select_related("organization", "owner")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create_project"] = user_can(self.request.user, self.module_code, "create")
        return ctx


class InvestProjectDetailView(InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestProject
    template_name = "invest/project_detail.html"
    context_object_name = "project"
    page_title = "Инвестпроект"

    def get_queryset(self):
        return projects_for_membership(self.get_membership()).select_related("organization", "owner")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        project = self.object
        package = ensure_package(project)
        items = list(package.items.order_by("id"))
        required = [i for i in items if i.required]
        ready = sum(1 for i in required if i.status == InvestPackageItem.Status.ATTACHED)
        ctx["can_change_project"] = user_can(self.request.user, self.module_code, "change")
        ctx["site_links"] = project.site_links.select_related("site", "site__organization").order_by("role", "id")
        ctx["roadmap_items"] = project.roadmap_items.select_related("owner").order_by("due_at", "code")
        ctx["package"] = package
        ctx["package_items"] = items
        ctx["package_ready"] = f"{ready}/{len(required)}" if required else "—"
        return ctx


class InvestHandoffListView(InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestHandoff
    template_name = "invest/handoffs_list.html"
    context_object_name = "handoffs"
    page_title = "Передачи в сопровождение"
    paginate_by = 25

    def get_queryset(self):
        projects = projects_for_membership(self.get_membership())
        return (
            InvestHandoff.objects.filter(project__in=projects)
            .select_related("project", "project__organization", "requested_by", "decided_by")
            .order_by("-created_at")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change_handoff"] = user_can(self.request.user, self.module_code, "change")
        return ctx


class InvestHandoffRequestView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"
    allowed_role_codes = {"invest_agency", "invest_admin"}

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        if not _membership_has_role(membership, self.allowed_role_codes):
            return _forbidden_with_message(request, "Передачу может запросить только агентство")
        project = get_object_or_404(projects_for_membership(membership), pk=kwargs["pk"])
        try:
            request_handoff(project=project, user=request.user, comment=request.POST.get("comment", ""))
        except InvestHandoffError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Передача запрошена.")
        return redirect(reverse("invest-handoffs"))


class InvestHandoffDecisionView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"
    allowed_role_codes = {"invest_dept", "invest_admin"}
    decision = ""
    success_message = ""

    def get_handoff(self):
        projects = projects_for_membership(self.get_membership())
        return get_object_or_404(InvestHandoff.objects.filter(project__in=projects), pk=self.kwargs["pk"])

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        if not _membership_has_role(membership, self.allowed_role_codes):
            return _forbidden_with_message(request, "Решение по передаче доступно только департаменту")
        handoff = self.get_handoff()
        try:
            if self.decision == "accept":
                accept_handoff(handoff=handoff, user=request.user)
            else:
                return_handoff(
                    handoff=handoff,
                    user=request.user,
                    comment=request.POST.get("comment", handoff.comment),
                )
        except InvestHandoffError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, self.success_message)
        return redirect(reverse("invest-handoffs"))


class InvestHandoffAcceptView(InvestHandoffDecisionView):
    decision = "accept"
    success_message = "Передача принята."


class InvestHandoffReturnView(InvestHandoffDecisionView):
    decision = "return"
    success_message = "Передача возвращена."


class InvestPackageDetailView(InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestProject
    template_name = "invest/package_detail.html"
    context_object_name = "project"
    page_title = "Пакет передачи"

    def get_queryset(self):
        return projects_for_membership(self.get_membership()).select_related("organization", "owner")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        package = ensure_package(self.object)
        ctx["package"] = package
        ctx["items"] = package.items.order_by("id")
        ctx["status_choices"] = InvestPackageItem.Status.choices
        ctx["can_change_package"] = user_can(self.request.user, self.module_code, "change")
        return ctx


class InvestPackageItemUpdateView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        project = get_object_or_404(projects_for_membership(self.get_membership()), pk=kwargs["project_pk"])
        package = ensure_package(project)
        item = get_object_or_404(package.items, pk=kwargs["item_pk"])
        status = request.POST.get("status")
        if status not in InvestPackageItem.Status.values:
            messages.error(request, "Некорректный статус пункта пакета.")
        else:
            set_item_status(item, status, request.FILES.get("file"))
            messages.success(request, "Пункт пакета обновлён.")
        return redirect(reverse("invest-package-detail", args=[project.pk]))


class InvestImportListView(InvestImportRoleMixin, InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestImportBatch
    template_name = "invest/import_list.html"
    context_object_name = "batches"
    page_title = "Импорт данных МО"
    paginate_by = 25
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return _import_batches_for_membership(self.get_membership()).order_by("-created_at")

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        upload = request.FILES.get("file")
        if not upload:
            messages.error(request, "Выберите CSV-файл для импорта.")
            return redirect(reverse("invest-imports"))

        batch = parse_mo_file(upload, subsystem=membership.subsystem, organization=membership.organization)
        messages.success(request, "Файл загружен. Проверьте строки перед применением.")
        return redirect(reverse("invest-import-detail", args=[batch.pk]))


class InvestImportDetailView(InvestImportRoleMixin, InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestImportBatch
    template_name = "invest/import_detail.html"
    context_object_name = "batch"
    page_title = "Пакет импорта"

    def get_queryset(self):
        return _import_batches_for_membership(self.get_membership())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rows"] = self.object.rows.select_related("target_project", "target_site").order_by("row_number")
        return ctx


class InvestImportRowActionView(InvestImportRoleMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    action = ""

    def post(self, request, *args, **kwargs):
        batch = get_object_or_404(_import_batches_for_membership(self.get_membership()), pk=kwargs["batch_pk"])
        row = get_object_or_404(batch.rows, pk=kwargs["row_pk"])
        try:
            if self.action == "apply":
                apply_row(row, user=request.user)
                messages.success(request, "Строка применена.")
            else:
                skip_row(row)
                messages.success(request, "Строка пропущена.")
        except ValueError as exc:
            messages.error(request, str(exc))

        if not batch.rows.filter(resolution=InvestImportRow.Resolution.PENDING).exists():
            batch.status = InvestImportBatch.Status.DONE
            batch.save(update_fields=["status"])
        return redirect(reverse("invest-import-detail", args=[batch.pk]))


class InvestImportRowApplyView(InvestImportRowActionView):
    action = "apply"


class InvestImportRowSkipView(InvestImportRowActionView):
    action = "skip"


class InvestProjectCreateView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, CreateView):
    model = InvestProject
    form_class = InvestProjectForm
    template_name = "invest/project_form.html"
    page_title = "Новый инвестпроект"
    required_action = "create"
    success_url = reverse_lazy("invest-projects")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership"] = self.get_membership()
        return kwargs

    def form_valid(self, form):
        form.instance.subsystem = self.get_subsystem()
        form.instance.funnel = InvestProject.Funnel.ATTRACTION
        membership = self.get_membership()
        if membership.role.code == "invest_mo":
            form.instance.organization = membership.organization
        messages.success(self.request, "Инвестпроект создан.")
        return super().form_valid(form)


class InvestProjectUpdateView(InvestSubsystemMixin, ModulePermissionMixin, UpdateView):
    model = InvestProject
    form_class = InvestProjectForm
    template_name = "invest/project_form.html"
    context_object_name = "project"
    page_title = "Редактирование инвестпроекта"
    required_action = "change"

    def get_queryset(self):
        return projects_for_membership(self.get_membership()).select_related("organization", "owner")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership"] = self.get_membership()
        return kwargs

    def get_success_url(self):
        return reverse_lazy("invest-project-detail", args=[self.object.pk])

    def form_valid(self, form):
        messages.success(self.request, "Инвестпроект обновлён.")
        return super().form_valid(form)


class InvestSiteListView(InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestSite
    template_name = "invest/sites_list.html"
    context_object_name = "sites"
    page_title = "Инвестплощадки"
    paginate_by = 25

    def get_queryset(self):
        return sites_for_membership(self.get_membership()).select_related("organization")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create_site"] = user_can(self.request.user, self.module_code, "create")
        ctx["can_change_site"] = user_can(self.request.user, self.module_code, "change")
        return ctx


class InvestSiteDetailView(InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestSite
    template_name = "invest/site_detail.html"
    context_object_name = "site"
    page_title = "Инвестплощадка"

    def get_queryset(self):
        return sites_for_membership(self.get_membership()).select_related("organization")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        membership = self.get_membership()
        ctx["can_change_site"] = user_can(self.request.user, self.module_code, "change")
        ctx["project_links"] = self.object.project_links.select_related("project", "project__organization")
        ctx["projects"] = projects_for_membership(membership).select_related("organization").order_by("code")
        ctx["smev_requests"] = self.object.smev_requests.all()[:10]
        ctx["smev_services"] = InvestSmevRequest.Service.choices
        return ctx


class InvestSiteCreateView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, CreateView):
    model = InvestSite
    form_class = InvestSiteForm
    template_name = "invest/site_form.html"
    page_title = "Новая инвестплощадка"
    required_action = "create"
    success_url = reverse_lazy("invest-sites")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership"] = self.get_membership()
        return kwargs

    def form_valid(self, form):
        form.instance.subsystem = self.get_subsystem()
        membership = self.get_membership()
        if membership.role.code == "invest_mo":
            form.instance.organization = membership.organization
        messages.success(self.request, "Инвестплощадка создана.")
        return super().form_valid(form)


class InvestSiteUpdateView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, UpdateView):
    model = InvestSite
    form_class = InvestSiteForm
    template_name = "invest/site_form.html"
    page_title = "Редактирование площадки"
    required_action = "change"

    def get_queryset(self):
        return sites_for_membership(self.get_membership())

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["membership"] = self.get_membership()
        return kwargs

    def get_success_url(self):
        return reverse("invest-site-detail", args=[self.object.pk])

    def form_valid(self, form):
        membership = self.get_membership()
        if membership.role.code == "invest_mo":
            form.instance.organization = membership.organization
        messages.success(self.request, "Площадка сохранена.")
        return super().form_valid(form)


class InvestSiteSmevRequestView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    """Тестовый запрос СМЭВ по площадке."""

    required_action = "change"

    def post(self, request, *args, **kwargs):
        site = get_object_or_404(sites_for_membership(self.get_membership()), pk=kwargs["pk"])
        service = request.POST.get("service") or InvestSmevRequest.Service.EGRN
        req = request_smev_fill(site=site, user=request.user, service=service)
        messages.success(
            request,
            f"Тестовый СМЭВ ({req.get_service_display()}): ответ получен. Можно применить к карточке.",
        )
        return redirect(reverse("invest-site-detail", args=[site.pk]))


class InvestSiteSmevApplyView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        site = get_object_or_404(sites_for_membership(self.get_membership()), pk=kwargs["pk"])
        smev_req = get_object_or_404(InvestSmevRequest, pk=kwargs["request_pk"], site=site)
        try:
            apply_smev_response(request=smev_req, user=request.user)
        except InvestSmevError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Данные тестового СМЭВ применены к карточке площадки.")
        return redirect(reverse("invest-site-detail", args=[site.pk]))


class InvestSiteActionView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"
    action_service = None
    success_message = ""

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        project = get_object_or_404(projects_for_membership(membership), pk=kwargs["project_pk"])
        site = get_object_or_404(sites_for_membership(membership), pk=kwargs["site_pk"])
        try:
            self.action_service(project=project, site=site, user=request.user)
        except InvestBookingError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, self.success_message)
        return redirect(reverse("invest-site-detail", args=[site.pk]))


class InvestSiteBookView(InvestSiteActionView):
    action_service = staticmethod(book_site)
    success_message = "Площадка забронирована."


class InvestSiteSelectView(InvestSiteActionView):
    action_service = staticmethod(select_site)
    success_message = "Площадка выбрана для проекта."
