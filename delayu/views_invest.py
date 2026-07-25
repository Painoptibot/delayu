"""Views for the invest subsystem."""

from django.contrib import messages
from django.contrib.auth.mixins import AccessMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.dateparse import parse_date
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView

from delayu.forms_invest import InvestProjectForm, InvestSiteForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import AuditLog, DocumentFile, Subsystem
from delayu.models_invest import (
    InvestExternalTask,
    InvestHandoff,
    InvestImportBatch,
    InvestImportRow,
    InvestInvestor,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestRoadmapItem,
    InvestSite,
    InvestSmevRequest,
)
from delayu.services.access import get_membership_or_403, user_can
from delayu.services import audit
from delayu.services.invest_booking import InvestBookingError, book_site, expire_overdue_bookings, select_site
from delayu.services.invest_dashboard import build_dashboard
from delayu.services.invest_dedup import ignore_duplicate_pair, suspected_duplicate_pairs
from delayu.services.invest_escalation import refresh_invest_sla
from delayu.services.invest_bitrix import InvestBitrixError, push_project_to_bitrix, resolve_bitrix_stage_conflict
from delayu.services.invest_gates import can_push_to_bitrix, compute_completeness, gate_blockers
from delayu.services.invest_handoff import (
    InvestHandoffError,
    RETURN_REASON_TEMPLATES,
    accept_handoff,
    request_handoff,
    resolve_return_comment,
    return_handoff,
)
from delayu.services.invest_import import apply_row, parse_mo_file, skip_row
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_package import ensure_package, set_item_status
from delayu.services.invest_scope import projects_for_membership, sites_for_membership
from delayu.services.invest_smev import InvestSmevError, apply_smev_response, request_smev_fill
from delayu.services.odysseus_invest import get_invest_odysseus_open_url, prepare_odysseus_open
from delayu.services.scope import is_platform_admin


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


def _with_odysseus_cta(request, ctx, *, membership, project=None, site=None):
    ctx["odysseus_cta_url"] = get_invest_odysseus_open_url(
        request,
        membership=membership,
        project=project,
        site=site,
    )
    return ctx


def _stage_to_funnel() -> dict[str, str]:
    result = {}
    for funnel, transitions in InvestProjectForm.STAGE_TRANSITIONS.items():
        for stage, allowed in transitions.items():
            result[stage] = funnel
            for next_stage in allowed:
                result[next_stage] = funnel
    return result


def _can_bulk_update_stage(user, membership) -> bool:
    return (
        getattr(user, "is_superuser", False)
        or is_platform_admin(user)
        or membership.role.code in {"invest_admin", "invest_dept"}
    )


def _completeness_actions(project, blockers):
    labels = {
        "name": "Добавьте наименование проекта",
        "investor_name": "Добавьте инвестора",
        "organization_id": "Укажите МО / территорию",
        "industry": "Добавьте отрасль",
        "package_incomplete": "Заполните обязательные пункты пакета",
        "mo_pending": "Закройте открытые задачи МО",
    }
    actions = [labels.get(blocker, blocker) for blocker in blockers]
    if not project.contact_person:
        actions.append("Добавьте контактное лицо")
    if not project.contact_phone:
        actions.append("Добавьте телефон контакта")
    if not project.description:
        actions.append("Добавьте описание проекта")
    if project.investment_amount is None:
        actions.append("Укажите объём инвестиций")
    return list(dict.fromkeys(actions))


def _coordinates_for_site(site):
    if site.latitude is not None and site.longitude is not None:
        return str(site.latitude), str(site.longitude)
    external = site.external_ids or {}
    coordinates = external.get("coordinates") or external.get("coords")
    if isinstance(coordinates, dict):
        lat = coordinates.get("lat") or coordinates.get("latitude")
        lon = coordinates.get("lon") or coordinates.get("lng") or coordinates.get("longitude")
        if lat and lon:
            return str(lat), str(lon)
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        return str(coordinates[0]), str(coordinates[1])
    if isinstance(coordinates, str) and "," in coordinates:
        lat, lon = coordinates.split(",", 1)
        return lat.strip(), lon.strip()
    return None, None


def _smev_payload_summary(payload):
    if not payload:
        return "—"
    keys = ("source", "area_ha", "vri", "land_category", "right_type", "received_at")
    parts = [f"{key}: {payload[key]}" for key in keys if payload.get(key)]
    if parts:
        return "; ".join(parts)
    return "; ".join(f"{key}: {value}" for key, value in list(payload.items())[:4])


class InvestHubView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/hub.html"
    page_title = "Обзор инвестконтура"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        membership = self.get_membership()
        projects = projects_for_membership(membership)
        ctx["stats"] = {
            "projects_total": projects.count(),
            "attraction": projects.filter(funnel=InvestProject.Funnel.ATTRACTION).count(),
            "support": projects.filter(funnel=InvestProject.Funnel.SUPPORT).count(),
        }
        ctx["recent_projects"] = projects.select_related("organization", "owner")[:8]
        ctx["can_create_project"] = user_can(self.request.user, self.module_code, "create")
        return _with_odysseus_cta(self.request, ctx, membership=membership)


class InvestDashboardView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/dashboard.html"
    page_title = "Дашборд руководителя"

    def get_dashboard_kwargs(self):
        return {
            "period": self.request.GET.get("period") or "",
            "date_from": parse_date(self.request.GET.get("from") or ""),
            "date_to": parse_date(self.request.GET.get("to") or ""),
        }

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["dashboard"] = build_dashboard(self.get_subsystem(), **self.get_dashboard_kwargs())
        ctx["period"] = self.request.GET.get("period") or "week"
        ctx["date_from"] = self.request.GET.get("from") or ""
        ctx["date_to"] = self.request.GET.get("to") or ""
        return ctx


class InvestDashboardExportView(InvestDashboardView):
    def get(self, request, *args, **kwargs):
        from openpyxl import Workbook
        from openpyxl.styles import Font

        dashboard = build_dashboard(self.get_subsystem(), **self.get_dashboard_kwargs())
        wb = Workbook()
        ws = wb.active
        ws.title = "Funnel"
        ws.append(["Воронка", "Стадия", "Проектов"])
        for funnel_name, counts in (
            ("Привлечение", dashboard["attraction_counts"]),
            ("Сопровождение", dashboard["support_counts"]),
        ):
            for stage, total in counts.items():
                ws.append([funnel_name, stage, total])

        overdue_ws = wb.create_sheet("Overdue")
        overdue_ws.append(["Показатель", "Значение"])
        overdue_ws.append(["Просрочено шагов", dashboard["overdue_count"]])
        overdue_ws.append(["Готовность пакетов, %", dashboard["packages_ready_pct"]])
        overdue_ws.append(["Активные брони", dashboard["active_bookings"]])

        bottlenecks_ws = wb.create_sheet("Bottlenecks")
        bottlenecks_ws.append(["МО", "Просрочено"])
        for row in dashboard["bottlenecks_by_org"]:
            bottlenecks_ws.append([row["organization_name"], row["overdue_count"]])

        industry_ws = wb.create_sheet("Industry")
        industry_ws.append(["Отрасль", "Проектов", "Инвестиции, млн руб.", "Рабочие места"])
        for row in dashboard["industry_metrics"]:
            industry_ws.append([row["industry"], row["projects"], row["investment_amount"], row["jobs"]])

        for sheet in wb.worksheets:
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for column in sheet.columns:
                letter = column[0].column_letter
                sheet.column_dimensions[letter].width = max(len(str(cell.value or "")) for cell in column) + 2

        response = HttpResponse(
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="invest-dashboard.xlsx"'
        wb.save(response)
        return response


class InvestKanbanView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/kanban.html"
    page_title = "Канбан инвестпроектов"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        projects = projects_for_membership(self.get_membership()).select_related("organization", "owner")
        kanban = {}
        for funnel, _label in InvestProject.Funnel.choices:
            kanban[funnel] = {}
            for project in projects.filter(funnel=funnel).order_by("stage", "code"):
                column = kanban[funnel].setdefault(
                    project.stage,
                    {
                        "stage": project.stage,
                        "label": InvestProjectForm.STAGE_LABELS.get(project.stage, project.stage),
                        "projects": [],
                    },
                )
                column["projects"].append(project)
        ctx["kanban"] = kanban
        return ctx


class InvestInboxView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/inbox.html"
    page_title = "Сегодня"
    http_method_names = ["get", "post", "head", "options"]

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "refresh_sla":
            result = refresh_invest_sla(
                subsystem=self.get_subsystem(),
                user=request.user,
                request=request,
            )
            messages.success(
                request,
                f"SLA обновлены: дорожная карта {result['roadmap']}, задачи {result['external_tasks']}.",
            )
        return redirect(reverse("invest-inbox"))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        membership = self.get_membership()
        projects = projects_for_membership(membership)
        now = timezone.now()
        ctx["roadmap_items"] = (
            InvestRoadmapItem.objects.filter(project__in=projects)
            .filter(Q(status=InvestRoadmapItem.Status.OVERDUE) | Q(status=InvestRoadmapItem.Status.OPEN, due_at__lt=now))
            .select_related("project", "project__organization", "owner")
            .order_by("due_at", "code")[:50]
        )
        ctx["handoffs"] = (
            InvestHandoff.objects.filter(project__in=projects, status=InvestHandoff.Status.REQUESTED)
            .select_related("project", "project__organization", "requested_by")
            .order_by("created_at")[:50]
        )
        ctx["external_tasks"] = (
            InvestExternalTask.objects.filter(
                project__in=projects,
                status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
            )
            .select_related("project", "organization")
            .order_by("due_at", "-created_at")[:50]
        )
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
        membership = self.get_membership()
        ctx["can_create_project"] = user_can(self.request.user, self.module_code, "create")
        ctx["can_bulk_stage"] = user_can(self.request.user, self.module_code, "change") and _can_bulk_update_stage(
            self.request.user, membership
        )
        ctx["bulk_stage_choices"] = [
            (stage, InvestProjectForm.STAGE_LABELS.get(stage, stage))
            for stage in _stage_to_funnel()
        ]
        return ctx


class InvestProjectBulkStageView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        if not _can_bulk_update_stage(request.user, membership):
            return _forbidden_with_message(request, "Массовая смена стадии доступна только администратору или департаменту")

        project_ids = request.POST.getlist("project_ids")
        new_stage = (request.POST.get("stage") or request.POST.get("new_stage") or "").strip()
        target_funnel = _stage_to_funnel().get(new_stage)
        if not project_ids or not target_funnel:
            messages.error(request, "Выберите проекты и корректную стадию.")
            return redirect(reverse("invest-projects"))

        projects = list(projects_for_membership(membership).filter(pk__in=project_ids).select_related("organization"))
        if len(projects) != len(set(project_ids)):
            messages.error(request, "Часть проектов недоступна в текущем контуре.")
            return redirect(reverse("invest-projects"))
        if any(project.funnel != target_funnel for project in projects):
            messages.error(request, "Массовая смена стадии разрешена только внутри той же воронки.")
            return redirect(reverse("invest-projects"))

        with transaction.atomic():
            for project in projects:
                old_stage = project.stage
                if old_stage == new_stage:
                    continue
                project.stage = new_stage
                project.save(update_fields=["stage", "updated_at"])
                audit.log_action(
                    request.user,
                    membership.subsystem,
                    "invest.project.bulk_stage",
                    model_name="InvestProject",
                    object_id=project.pk,
                    payload={"old_stage": old_stage, "new_stage": new_stage},
                    request=request,
                )
        messages.success(request, f"Стадия обновлена для {len(projects)} проектов.")
        return redirect(reverse("invest-projects"))


class InvestProjectDetailView(InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestProject
    template_name = "invest/project_detail.html"
    context_object_name = "project"
    page_title = "Инвестпроект"

    def get_queryset(self):
        return projects_for_membership(self.get_membership()).select_related("organization", "owner")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        membership = self.get_membership()
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
        blockers = gate_blockers(project)
        can_push, bitrix_blockers = can_push_to_bitrix(project)
        ctx["bitrix_can_push"] = can_push
        ctx["bitrix_blockers"] = bitrix_blockers
        ctx["bitrix_stage_conflict"] = (project.external_ids or {}).get("bitrix_stage_conflict")
        ctx["completeness_pct"] = compute_completeness(project)
        ctx["completeness_actions"] = _completeness_actions(project, blockers)
        ctx["audit_logs"] = AuditLog.objects.filter(
            subsystem=project.subsystem,
            model_name__iexact="InvestProject",
            object_id=str(project.pk),
        )[:20]
        return _with_odysseus_cta(self.request, ctx, membership=membership, project=project)


class InvestProjectBitrixPushView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        project = get_object_or_404(projects_for_membership(self.get_membership()), pk=kwargs["pk"])
        try:
            result = push_project_to_bitrix(project=project, force=False)
        except InvestBitrixError as exc:
            messages.error(request, str(exc))
        else:
            if result.get("pushed"):
                messages.success(request, "Проект отправлен в Bitrix.")
            else:
                messages.warning(request, "Отправка в Bitrix заблокирована: " + ", ".join(result.get("blockers") or []))
        return redirect(reverse("invest-project-detail", args=[project.pk]))


class InvestProjectBitrixConflictView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        project = get_object_or_404(projects_for_membership(self.get_membership()), pk=kwargs["pk"])
        resolution = request.POST.get("resolution") or ""
        try:
            result = resolve_bitrix_stage_conflict(project=project, resolution=resolution)
        except InvestBitrixError as exc:
            messages.error(request, str(exc))
        else:
            if result.get("resolved"):
                messages.success(request, "Конфликт стадий Bitrix/Delayu разрешён.")
            else:
                messages.info(request, "Активного конфликта стадий нет.")
        return redirect(reverse("invest-project-detail", args=[project.pk]))


class InvestInvestorListView(InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestInvestor
    template_name = "invest/investors_list.html"
    context_object_name = "investors"
    page_title = "Юрлица инвесторов"
    paginate_by = 25

    def get_queryset(self):
        return (
            InvestInvestor.objects.filter(subsystem=self.get_subsystem())
            .prefetch_related("projects")
            .order_by("name")
        )


class InvestInvestorDetailView(InvestSubsystemMixin, ModulePermissionMixin, DetailView):
    model = InvestInvestor
    template_name = "invest/investor_detail.html"
    context_object_name = "investor"
    page_title = "Юрлицо инвестора"

    def get_queryset(self):
        return InvestInvestor.objects.filter(subsystem=self.get_subsystem())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        membership = self.get_membership()
        ctx["projects"] = projects_for_membership(membership).filter(investor_entity=self.object)
        return ctx


class InvestDedupeView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/dedupe.html"
    page_title = "Дедупликация проектов"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["pairs"] = suspected_duplicate_pairs(self.get_subsystem())
        ctx["can_change_dedupe"] = user_can(self.request.user, self.module_code, "change")
        return ctx


class InvestDedupeIgnoreView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request, *args, **kwargs):
        membership = self.get_membership()
        projects = projects_for_membership(membership)
        left = get_object_or_404(projects, pk=request.POST.get("left_id"))
        right = get_object_or_404(projects, pk=request.POST.get("right_id"))
        ignore_duplicate_pair(left, right)
        messages.success(request, "Пара дублей скрыта.")
        return redirect(reverse("invest-dedupe"))


class InvestOdysseusOpenView(InvestSubsystemMixin, ModulePermissionMixin, View):
    """Prepare an Invest context snapshot before redirecting to Odysseus."""

    def get(self, request, *args, **kwargs):
        membership = self.get_membership()
        project = None
        site = None
        if request.GET.get("project"):
            project = get_object_or_404(projects_for_membership(membership), pk=request.GET["project"])
        if request.GET.get("site"):
            site = get_object_or_404(sites_for_membership(membership), pk=request.GET["site"])
        try:
            return redirect(
                prepare_odysseus_open(
                    request,
                    membership=membership,
                    project=project,
                    site=site,
                )
            )
        except PermissionError as exc:
            return HttpResponseForbidden(str(exc))

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


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
        ctx["return_reason_templates"] = RETURN_REASON_TEMPLATES
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
                    comment=resolve_return_comment(
                        template_key=request.POST.get("comment_template", ""),
                        comment=request.POST.get("comment", ""),
                        fallback=handoff.comment,
                    ),
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
        ctx["items"] = package.items.select_related("document").order_by("id")
        ctx["snapshots"] = package.snapshots.select_related("handoff").order_by("-created_at")
        ctx["status_choices"] = InvestPackageItem.Status.choices
        ctx["can_change_package"] = user_can(self.request.user, self.module_code, "change")
        ctx["recent_documents"] = DocumentFile.objects.filter(
            subsystem=self.get_subsystem(),
            is_current=True,
        ).order_by("-created_at")[:25]
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
            document = None
            document_id = request.POST.get("document")
            if document_id:
                document = get_object_or_404(DocumentFile, pk=document_id, subsystem=self.get_subsystem())
            set_item_status(item, status, request.FILES.get("file"), document)
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


class InvestSiteMapView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/sites_map.html"
    page_title = "Карта инвестплощадок"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sites = sites_for_membership(self.get_membership()).select_related("organization")
        mapped_sites = []
        for site in sites:
            lat, lon = _coordinates_for_site(site)
            mapped_sites.append({"site": site, "latitude": lat, "longitude": lon, "has_coordinates": bool(lat and lon)})
        ctx["mapped_sites"] = mapped_sites
        ctx["has_coordinates"] = any(entry["has_coordinates"] for entry in mapped_sites)
        return ctx


class InvestSiteCompareView(InvestSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "invest/sites_compare.html"
    page_title = "Сравнение площадок"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        raw_ids = (self.request.GET.get("ids") or "").replace(";", ",").split(",")
        ids = []
        for raw_id in raw_ids:
            if raw_id.strip().isdigit():
                ids.append(int(raw_id.strip()))
            if len(ids) == 3:
                break
        sites = list(
            sites_for_membership(self.get_membership())
            .filter(pk__in=ids)
            .select_related("organization")
        )
        site_by_id = {site.pk: site for site in sites}
        ctx["sites"] = [site_by_id[site_id] for site_id in ids if site_id in site_by_id]
        ctx["requested_ids"] = ",".join(str(site_id) for site_id in ids)
        return ctx


class InvestBookingsView(InvestForbiddenResponseMixin, InvestSubsystemMixin, ModulePermissionMixin, ListView):
    model = InvestProjectSite
    template_name = "invest/bookings.html"
    context_object_name = "bookings"
    page_title = "Брони площадок"
    required_action = "change"
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        membership = self.get_membership()
        return (
            InvestProjectSite.objects.filter(
                project__in=projects_for_membership(membership),
                site__in=sites_for_membership(membership),
                role__in=(InvestProjectSite.Role.BOOKED, InvestProjectSite.Role.SELECTED),
            )
            .select_related("project", "project__organization", "site", "site__organization")
            .order_by("booked_until", "project__code", "site__cadastral_number")
        )

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "expire":
            expired = expire_overdue_bookings(subsystem=self.get_subsystem())
            messages.success(request, f"Просроченные брони сняты: {expired}.")
        return redirect(reverse("invest-bookings"))


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
        flags = ensure_automation_config(self.object.subsystem).get_flags()
        ctx["smev_live_pending_mode"] = bool(flags.get("smev_live") and not flags.get("smev_mock"))
        egrn_requests = self.object.smev_requests.filter(service=InvestSmevRequest.Service.EGRN)[:10]
        ctx["egrn_history"] = [
            {
                "request": request,
                "payload_summary": _smev_payload_summary(request.response_payload),
            }
            for request in egrn_requests
        ]
        ctx["smev_services"] = InvestSmevRequest.Service.choices
        return _with_odysseus_cta(self.request, ctx, membership=membership, site=self.object)


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
        if req.status == InvestSmevRequest.Status.LIVE_PENDING:
            messages.info(request, f"СМЭВ live ({req.get_service_display()}): запрос ожидает ответа шлюза.")
        else:
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
