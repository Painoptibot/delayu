"""Views for the invest subsystem."""

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from delayu.forms_invest import InvestProjectForm, InvestSiteForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import Subsystem
from delayu.models_invest import InvestHandoff, InvestPackageItem, InvestProject, InvestSite
from delayu.services.access import get_membership_or_403, user_can
from delayu.services.invest_booking import InvestBookingError, book_site, select_site
from delayu.services.invest_handoff import (
    InvestHandoffError,
    accept_handoff,
    request_handoff,
    return_handoff,
)
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.services.invest_scope import projects_for_membership, sites_for_membership


class InvestSubsystemMixin:
    module_code = "M22"
    page_title = "Инвестконтур"

    def get_membership(self):
        if not hasattr(self, "_invest_membership"):
            self._invest_membership = get_membership_or_403(self.request)
        return self._invest_membership

    def get_subsystem(self):
        return self.get_membership().subsystem

    def dispatch(self, request, *args, **kwargs):
        membership = get_membership_or_403(request)
        if (
            membership.subsystem.industry_template != "invest"
            or membership.subsystem.status != Subsystem.Status.ACTIVE
        ):
            raise PermissionDenied("Раздел доступен только в активном инвестконтуре")
        self._invest_membership = membership
        return super().dispatch(request, *args, **kwargs)


class InvestForbiddenResponseMixin:
    def dispatch(self, request, *args, **kwargs):
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not user_can(
            request.user, self.module_code, self.required_action
        ):
            return HttpResponseForbidden(f"Нет доступа к {self.module_code}")
        return super().dispatch(request, *args, **kwargs)


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
        ctx["can_change_project"] = user_can(self.request.user, self.module_code, "change")
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

    def post(self, request, *args, **kwargs):
        project = get_object_or_404(projects_for_membership(self.get_membership()), pk=kwargs["pk"])
        try:
            request_handoff(project=project, user=request.user, comment=request.POST.get("comment", ""))
        except InvestHandoffError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Передача запрошена.")
        return redirect(reverse("invest-handoffs"))


class InvestHandoffDecisionView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"
    decision = ""
    success_message = ""

    def get_handoff(self):
        projects = projects_for_membership(self.get_membership())
        return get_object_or_404(InvestHandoff.objects.filter(project__in=projects), pk=self.kwargs["pk"])

    def post(self, request, *args, **kwargs):
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
        messages.success(self.request, "Инвестплощадка создана.")
        return super().form_valid(form)


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
