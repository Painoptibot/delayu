"""Представления АИС УЖВ (контур подсистемы)."""
import json
from datetime import date, timedelta

from django.contrib import messages
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView

from delayu.forms_uzhv import (
    HousingAdminProtocolForm,
    HousingAppealForm,
    HousingAppealRegisterForm,
    HousingAppealAttachmentForm,
    HousingCaseAttachmentForm,
    HousingCitizenForm,
    HousingContractForm,
    HousingContractAttachmentForm,
    HousingContractConsentForm,
    HousingCourtCaseForm,
    HousingHouseholdMemberFormSet,
    HousingInspectionForm,
    HousingInspectionOrderForm,
    HousingInspectionPlanForm,
    HousingEnforcementProceedingForm,
    HousingInteragencyRequestForm,
    HousingPersonalAccountForm,
    HousingPersonalAccountMemberForm,
    PrivateManagedPremiseForm,
    HousingPrescriptionForm,
    HousingQueueCaseForm,
    MunicipalBuildingForm,
    MunicipalPremiseForm,
)
from delayu.mixins import ModulePermissionMixin
from delayu.models_uzhv import (
    HousingAdminProtocol,
    HousingAppeal,
    HousingCitizen,
    HousingContract,
    HousingCourtCase,
    HousingEnforcementProceeding,
    HousingInspection,
    HousingInspectionOrder,
    HousingInspectionPlan,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingCaseAttachment,
    HousingContractAttachment,
    HousingContractConsent,
    HousingPersonalAccount,
    HousingPersonalAccountMember,
    PrivateManagedPremise,
    HousingQueueCase,
    MunicipalBuilding,
    MunicipalPremise,
    OrphanHousingRecord,
    YoungFamilyRecord,
)
from delayu.services.access import get_membership_or_403, user_can
from delayu.services.uzhv_control import sync_overdue_prescriptions
from delayu.services.uzhv_export import http_export_report
from delayu.services.uzhv_interagency import next_interagency_number, sync_overdue_interagency
from delayu.services.uzhv import (
    filter_appeals,
    next_case_number,
    next_contract_number,
    next_inspection_number,
    next_inspection_plan_number,
    next_inspection_order_number,
    register_housing_appeal,
)
from delayu.services.uzhv_case_package import build_case_zip_bytes, build_orphan_package_bytes
from delayu.services.uzhv_contracts import save_housing_contract
from delayu.services.uzhv_documents import (
    render_appeal_document,
    render_case_document,
    render_consent_document,
    render_personal_account_document,
    text_to_docx_bytes,
)
from delayu.services.uzhv_inspection_orders import (
    complete_inspection_order_for_inspection,
    spawn_inspection_from_order,
)
from delayu.services.uzhv_personal_account import ensure_personal_account, record_account_history
from delayu.services.uzhv_queue import (
    REGISTRY_MUNICIPAL_CATEGORIES,
    REGISTRY_SPECIAL_CATEGORIES,
    recalculate_housing_queue,
)
from delayu.services.uzhv_import import import_contracts_xlsx
from delayu.services.uzhv_low_income import (
    compute_low_income_review_due,
    get_low_income_review_days,
    get_subsistence_minimum,
)
from delayu.services.uzhv_low_income_decision import (
    apply_low_income_calculation,
    reject_low_income_application,
    sync_applicant_to_household,
)
from delayu.services.uzhv_reports import REPORT_BUILDERS

User = get_user_model()


class UzhvSubsystemMixin:
    module_code = "M22"
    page_title = "АИС УЖВ"

    def get_subsystem(self):
        return get_membership_or_403(self.request).subsystem

    def dispatch(self, request, *args, **kwargs):
        mem = get_membership_or_403(request)
        if mem.subsystem.industry_template != "uzhv":
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Раздел доступен только в контуре АИС УЖВ")
        return super().dispatch(request, *args, **kwargs)


def _can(user, action="view"):
    return user_can(user, "M22", action)


class UzhvHubView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/hub.html"
    page_title = "Обзор АИС УЖВ"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        today = timezone.now().date()
        user = self.request.user
        from delayu.services.uzhv_bulk import subsystem_assignees
        from delayu.services.uzhv_overdue import (
            interagency_assignee_q,
            list_overdue_items,
            parse_hub_assignee_filter,
        )

        assignee_id = parse_hub_assignee_filter(self.request.GET, user)
        appeals_open = HousingAppeal.objects.filter(subsystem=sub).exclude(
            status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
        )
        ctx["stats"] = {
            "cases_active": HousingQueueCase.objects.filter(
                subsystem=sub,
                status__in=[
                    HousingQueueCase.Status.REGISTERED,
                    HousingQueueCase.Status.QUEUED,
                ],
            ).count(),
            "citizens": HousingCitizen.objects.filter(subsystem=sub).count(),
            "buildings": MunicipalBuilding.objects.filter(subsystem=sub).count(),
            "premises_free": MunicipalPremise.objects.filter(
                building__subsystem=sub, status=MunicipalPremise.Status.FREE
            ).count(),
            "contracts_active": HousingContract.objects.filter(
                subsystem=sub, is_active=True
            ).count(),
            "appeals_open": appeals_open.count(),
            "appeals_overdue": appeals_open.filter(due_date__lt=today).count(),
            "inspections_open": HousingInspection.objects.filter(
                subsystem=sub,
                status__in=[
                    HousingInspection.Status.PLANNED,
                    HousingInspection.Status.IN_PROGRESS,
                ],
            ).count(),
            "prescriptions_overdue": HousingPrescription.objects.filter(
                inspection__subsystem=sub,
                due_date__lt=today,
            )
            .exclude(
                status__in=[
                    HousingPrescription.Status.FULFILLED,
                    HousingPrescription.Status.CANCELLED,
                ]
            )
            .count(),
            "resettlement_buildings": MunicipalBuilding.objects.filter(
                subsystem=sub,
            )
            .filter(
                Q(in_resettlement_program=True)
                | Q(condition=MunicipalBuilding.Condition.EMERGENCY)
                | Q(condition=MunicipalBuilding.Condition.RENOVATION)
            )
            .count(),
            "court_cases_open": HousingCourtCase.objects.filter(
                subsystem=sub,
            )
            .exclude(
                status__in=[
                    HousingCourtCase.Status.CLOSED,
                    HousingCourtCase.Status.CANCELLED,
                ]
            )
            .count(),
            "interagency_awaiting": HousingInteragencyRequest.objects.filter(
                subsystem=sub,
                status__in=[
                    HousingInteragencyRequest.Status.SENT,
                    HousingInteragencyRequest.Status.AWAITING,
                    HousingInteragencyRequest.Status.OVERDUE,
                ],
            ).count(),
            "interagency_overdue": HousingInteragencyRequest.objects.filter(
                subsystem=sub,
                due_date__lt=today,
            )
            .exclude(
                status__in=[
                    HousingInteragencyRequest.Status.ANSWERED,
                    HousingInteragencyRequest.Status.CANCELLED,
                ]
            )
            .count(),
            "admin_protocols": HousingAdminProtocol.objects.filter(
                inspection__subsystem=sub
            ).count(),
        }
        ctx["recent_cases"] = (
            HousingQueueCase.objects.filter(subsystem=sub)
            .select_related("citizen", "assignee")
            .order_by("-updated_at")[:8]
        )
        urgent_qs = appeals_open.filter(
            due_date__lte=today + timedelta(days=5)
        ).select_related("citizen", "assignee")
        if assignee_id:
            urgent_qs = urgent_qs.filter(assignee_id=assignee_id)
        ctx["urgent_appeals"] = urgent_qs.order_by("due_date")[:5]
        pres_qs = (
            HousingPrescription.objects.filter(
                inspection__subsystem=sub,
                due_date__lt=today,
            )
            .exclude(
                status__in=[
                    HousingPrescription.Status.FULFILLED,
                    HousingPrescription.Status.CANCELLED,
                ]
            )
            .select_related("inspection", "inspection__building", "inspection__inspector")
            .order_by("due_date")
        )
        if assignee_id:
            pres_qs = pres_qs.filter(inspection__inspector_id=assignee_id)
        ctx["overdue_prescriptions"] = pres_qs[:5]
        if user.is_authenticated:
            ctx["my_cases"] = (
                HousingQueueCase.objects.filter(subsystem=sub, assignee=user)
                .exclude(
                    status__in=[
                        HousingQueueCase.Status.PROVIDED,
                        HousingQueueCase.Status.REMOVED,
                        HousingQueueCase.Status.REJECTED,
                    ]
                )
                .select_related("citizen")
                .order_by("-updated_at")[:5]
            )
            ctx["my_appeals"] = (
                appeals_open.filter(assignee=user)
                .select_related("citizen")
                .order_by("due_date")[:5]
            )
        else:
            ctx["my_cases"] = []
            ctx["my_appeals"] = []
        inter_qs = (
            HousingInteragencyRequest.objects.filter(
                subsystem=sub,
                due_date__lt=today,
            )
            .exclude(
                status__in=[
                    HousingInteragencyRequest.Status.ANSWERED,
                    HousingInteragencyRequest.Status.CANCELLED,
                ]
            )
            .select_related("citizen", "housing_case", "housing_case__assignee", "created_by")
            .order_by("due_date")
        )
        if assignee_id:
            inter_qs = inter_qs.filter(interagency_assignee_q(assignee_id))
        ctx["overdue_interagency"] = inter_qs[:5]
        ctx["overdue_items"] = list_overdue_items(sub, assignee_id=assignee_id, limit=20)
        ctx["hub_assignee_users"] = subsystem_assignees(sub)
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        from delayu.services.uzhv_deadlines import upcoming_deadlines

        ctx["week_deadlines"] = upcoming_deadlines(sub, days=7, limit=12)
        if self.request.user.is_authenticated:
            from delayu.models import Notification
            from delayu.services.uzhv_notifications import (
                mark_uzhv_notifications_synced,
                should_sync_uzhv_notifications,
                sync_uzhv_deadline_notifications,
            )

            ctx["uzhv_unread_notifications"] = Notification.objects.filter(
                user=self.request.user,
                subsystem=sub,
                is_read=False,
            ).count()
            if should_sync_uzhv_notifications(self.request, sub):
                result = sync_uzhv_deadline_notifications(sub)
                mark_uzhv_notifications_synced(self.request, sub)
                n = result["created"]
                if n:
                    messages.info(
                        self.request,
                        f"Создано уведомлений по срокам: {n}. См. колокольчик в шапке.",
                    )
                    ctx["uzhv_unread_notifications"] = Notification.objects.filter(
                        user=self.request.user,
                        subsystem=sub,
                        is_read=False,
                    ).count()
        else:
            ctx["uzhv_unread_notifications"] = 0
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["show_create_hub"] = ctx["can_create"] or user_can(
            self.request.user, "M24", "create"
        )
        from delayu.services.uzhv_workload import build_assignee_workload

        ctx["workload_rows"] = build_assignee_workload(sub)[:10]
        from django.urls import reverse

        ctx["subsystem_code"] = sub.code
        ctx["public_appeal_path"] = reverse("uzhv-public-appeal", args=[sub.code])
        ctx["public_appeal_url"] = self.request.build_absolute_uri(ctx["public_appeal_path"])
        if self.request.GET.get("dismiss") == "push_banner":
            self.request.session["uzhv_push_banner_dismiss"] = True
            self.request.session.modified = True
        if self.request.user.is_authenticated:
            from delayu.services.uzhv_pwa import push_subscription_status, user_has_uzhv_membership

            push_status = push_subscription_status(self.request.user)
            ctx["uzhv_push_status"] = push_status
            ctx["show_uzhv_push_banner"] = (
                user_has_uzhv_membership(self.request.user)
                and not push_status["subscribed"]
                and not self.request.session.get("uzhv_push_banner_dismiss")
            )
        return ctx


class UzhvServiceWorkerView(View):
    """Service Worker для Web Push и уведомлений УЖВ."""

    def get(self, request):
        from django.conf import settings
        from django.http import HttpResponse

        path = settings.BASE_DIR / "src" / "assets" / "js" / "delayu-uzhv-sw.js"
        resp = HttpResponse(path.read_text(encoding="utf-8"), content_type="application/javascript")
        resp["Service-Worker-Allowed"] = "/"
        resp["Cache-Control"] = "no-cache"
        return resp


class UzhvMobileAlertsView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    """JSON для PWA: просрочки и непрочитанные уведомления."""

    def get(self, request):
        from django.http import JsonResponse

        from delayu.services.uzhv_pwa import uzhv_user_alerts

        sub = self.get_subsystem()
        return JsonResponse(uzhv_user_alerts(sub, request.user))


class UzhvPushSubscribeView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    """Сохранение Web Push subscription пользователя."""

    def post(self, request):
        import json

        from django.http import JsonResponse

        from delayu.services.uzhv_pwa import save_push_subscription

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "invalid json"}, status=400)
        ok = save_push_subscription(request.user, payload)
        return JsonResponse({"ok": ok})

    def delete(self, request):
        from django.http import JsonResponse

        from delayu.services.uzhv_pwa import clear_push_subscription

        clear_push_subscription(request.user)
        return JsonResponse({"ok": True})


class UzhvPushTestView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    """Тестовое Web Push / локальное уведомление для текущего пользователя."""

    def post(self, request):
        from django.http import JsonResponse

        from delayu.services.uzhv_webpush import send_uzhv_web_push

        ok = send_uzhv_web_push(
            request.user,
            title="АИС УЖВ: тест",
            body="Push-канал работает. Просрочки будут приходить сюда.",
            url="/uzhv/",
        )
        return JsonResponse({"ok": ok, "push": ok})


class UzhvWorkloadExportView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    module_code = "M15"

    def get(self, request):
        from delayu.services.uzhv_workload import export_workload_xlsx

        return export_workload_xlsx(self.get_subsystem())


class UzhvAssigneeDashboardView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/assignee_dashboard.html"
    page_title = "Исполнитель"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        assignee = get_object_or_404(User, pk=kwargs["user_id"])
        from delayu.services.uzhv_bulk import subsystem_assignees
        from delayu.services.uzhv_overdue import list_overdue_items
        from delayu.services.uzhv_workload import assignee_workload_row

        allowed = {u.pk for u in subsystem_assignees(sub)}
        if assignee.pk not in allowed:
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Исполнитель не в контуре подсистемы")
        row = assignee_workload_row(sub, assignee.pk)
        if not row:
            from django.http import Http404

            raise Http404()
        ctx["assignee"] = assignee
        ctx["workload"] = row
        ctx["overdue_items"] = list_overdue_items(sub, assignee_id=assignee.pk, limit=50)
        label = assignee.get_full_name() or assignee.username
        ctx["page_title"] = f"Исполнитель: {label}"
        return ctx


class UzhvDeadlinesCalendarView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/deadlines_calendar.html"
    page_title = "Календарь сроков"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        from delayu.services.uzhv_deadlines import (
            _week_start,
            deadlines_for_month,
            deadlines_grouped,
        )

        today = timezone.now().date()
        view_mode = self.request.GET.get("view", "week")
        if view_mode not in ("week", "month"):
            view_mode = "week"
        ctx["view_mode"] = view_mode
        ctx["today"] = today
        ctx["kind_legend"] = [
            ("appeal", "Обращения"),
            ("prescription", "Предписания"),
            ("interagency", "Межвед"),
            ("court", "Суд"),
        ]

        if view_mode == "month":
            raw_month = self.request.GET.get("month", "").strip()
            try:
                month_day = (
                    date.fromisoformat(raw_month + "-01")
                    if raw_month and len(raw_month) == 7
                    else today.replace(day=1)
                )
            except ValueError:
                month_day = today.replace(day=1)
            prev_m = (month_day.replace(day=1) - timedelta(days=1)).replace(day=1)
            if month_day.month == 12:
                next_m = month_day.replace(year=month_day.year + 1, month=1, day=1)
            else:
                next_m = month_day.replace(month=month_day.month + 1, day=1)
            ctx["month_value"] = month_day.strftime("%Y-%m")
            ctx["month_day"] = month_day
            ctx["prev_month"] = prev_m.strftime("%Y-%m")
            ctx["next_month"] = next_m.strftime("%Y-%m")
            ctx["events_json"] = json.dumps(
                deadlines_for_month(sub, month_day), ensure_ascii=False
            )
            return ctx

        raw = self.request.GET.get("start", "").strip()
        try:
            start = date.fromisoformat(raw) if raw else _week_start(today)
        except ValueError:
            start = _week_start(today)
        ctx["week_start"] = start
        ctx["week_end"] = start + timedelta(days=6)
        ctx["prev_week"] = (start - timedelta(days=7)).isoformat()
        ctx["next_week"] = (start + timedelta(days=7)).isoformat()
        ctx["deadline_groups"] = deadlines_grouped(sub, start=start, days=7)
        return ctx


class UzhvDeadlinesExportView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request):
        from delayu.services.uzhv_deadlines import export_deadlines_csv, export_deadlines_ical

        sub = self.get_subsystem()
        fmt = request.GET.get("format", "csv")
        try:
            days = min(90, max(7, int(request.GET.get("days", 30))))
        except ValueError:
            days = 30
        if fmt == "ical":
            return export_deadlines_ical(sub, days=days)
        return export_deadlines_csv(sub, days=days)


class UzhvOverdueExportView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request):
        from delayu.services.uzhv_overdue import (
            export_overdue_csv,
            export_overdue_xlsx,
            parse_hub_assignee_filter,
        )

        sub = self.get_subsystem()
        assignee_id = parse_hub_assignee_filter(request.GET, request.user)
        if request.GET.get("format") == "xlsx":
            return export_overdue_xlsx(sub, assignee_id=assignee_id)
        return export_overdue_csv(sub, assignee_id=assignee_id)


class UzhvCasesListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/cases_list.html"
    page_title = "Учёт нуждающихся"
    context_object_name = "cases"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        from delayu.services.uzhv_overdue import parse_hub_assignee_filter

        assignee_id = parse_hub_assignee_filter(self.request.GET, self.request.user)
        qs = HousingQueueCase.objects.filter(subsystem=sub).select_related(
            "citizen", "assignee"
        )
        if assignee_id:
            qs = qs.filter(assignee_id=assignee_id)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(case_number__icontains=q)
                | Q(citizen__last_name__icontains=q)
                | Q(citizen__first_name__icontains=q)
            )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        category = self.request.GET.get("category", "").strip()
        if category:
            qs = qs.filter(category=category)
        registry = self.request.GET.get("registry", "").strip()
        if registry == "municipal":
            qs = qs.filter(category__in=REGISTRY_MUNICIPAL_CATEGORIES)
        elif registry == "special":
            qs = qs.filter(category__in=REGISTRY_SPECIAL_CATEGORIES)
        return qs.order_by("queue_position", "-registered_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = HousingQueueCase.Status.choices
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "cases"
        ctx["bulk_status_choices"] = HousingQueueCase.Status.choices
        from delayu.services.uzhv_bulk import subsystem_assignees

        ctx["bulk_show_assignee"] = True
        ctx["bulk_assignee_users"] = subsystem_assignees(self.get_subsystem())
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        ctx["filter_category"] = self.request.GET.get("category", "")
        ctx["filter_registry"] = self.request.GET.get("registry", "")
        ctx["category_choices"] = HousingQueueCase.Category.choices
        ctx["can_recalc_queue"] = _can(self.request.user, "change")
        ctx["case_assignee_users"] = ctx["bulk_assignee_users"]
        return ctx


class UzhvQueueRecalcView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    required_action = "change"

    def post(self, request):
        sub = self.get_subsystem()
        dry_run = request.POST.get("dry_run") == "1"
        result = recalculate_housing_queue(sub, dry_run=dry_run)
        mode = " (dry-run)" if dry_run else ""
        messages.success(
            request,
            f"Очередь пересчитана{mode}: в очереди {result.total}, изменено {result.updated}",
        )
        return redirect(request.POST.get("next") or "uzhv-cases")


class UzhvCaseModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase.objects.select_related("citizen", "assignee"),
            pk=pk,
            subsystem=sub,
        )
        from delayu.services.uzhv_timeline import build_case_timeline

        return render(
            request,
            "platform/uzhv/_case_modal.html",
            {
                "case": case,
                "can_change": _can(request.user, "change"),
                "timeline": build_case_timeline(case, request=request),
                "appeals_count": case.appeals.count(),
                "attachments_count": case.attachments.count(),
            },
        )


class UzhvCaseCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/case_form.html"
    page_title = "Новое учётное дело"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        ctx["form"] = kwargs.get(
            "form",
            HousingQueueCaseForm(
                subsystem=sub,
                initial={
                    "case_number": next_case_number(sub),
                    "registered_at": timezone.now().date(),
                },
            ),
        )
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingQueueCaseForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            from delayu.services.uzhv_case_status import record_case_status_change

            record_case_status_change(
                obj,
                old_status="",
                new_status=obj.status,
                user=request.user,
                comment="Создание дела",
            )
            if obj.status in (
                HousingQueueCase.Status.REGISTERED,
                HousingQueueCase.Status.QUEUED,
            ):
                recalculate_housing_queue(sub)
            messages.success(request, f"Дело {obj.case_number} создано")
            return redirect("uzhv-cases")
        ctx = self.get_context_data(form=form)
        return self.render_to_response(ctx)


class UzhvCaseUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/case_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        case = get_object_or_404(HousingQueueCase, pk=self.kwargs["pk"], subsystem=sub)
        ctx["case"] = case
        ctx["page_title"] = f"Редактирование {case.case_number}"
        ctx["form"] = HousingQueueCaseForm(instance=case, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(HousingQueueCase, pk=pk, subsystem=sub)
        form = HousingQueueCaseForm(request.POST, instance=case, subsystem=sub)
        if form.is_valid():
            old_status = case.status
            obj = form.save(commit=False)
            if obj.status == HousingQueueCase.Status.REMOVED and not obj.removed_at:
                obj.removed_at = timezone.now().date()
            obj.save()
            from delayu.services.uzhv_case_status import (
                build_removal_comment,
                record_case_status_change,
            )

            comment = build_removal_comment(obj) if obj.status == HousingQueueCase.Status.REMOVED else ""
            record_case_status_change(
                obj,
                old_status=old_status,
                new_status=obj.status,
                user=request.user,
                comment=comment,
            )
            if old_status != obj.status or "registered_at" in form.changed_data or "category" in form.changed_data:
                recalculate_housing_queue(sub)
            messages.success(request, "Дело сохранено")
            return redirect("uzhv-cases")
        return self.render_to_response({**self.get_context_data(), "form": form, "case": case})


class UzhvCitizenUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/citizen_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        citizen = get_object_or_404(HousingCitizen, pk=self.kwargs["pk"], subsystem=sub)
        ctx["citizen"] = citizen
        ctx["page_title"] = citizen.full_name
        ctx["form"] = HousingCitizenForm(instance=citizen)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        citizen = get_object_or_404(HousingCitizen, pk=pk, subsystem=sub)
        form = HousingCitizenForm(request.POST, instance=citizen)
        if form.is_valid():
            form.save()
            messages.success(request, "Данные гражданина сохранены")
            return redirect("uzhv-citizens")
        return self.render_to_response({**self.get_context_data(), "form": form, "citizen": citizen})


class UzhvCitizensListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/citizens_list.html"
    page_title = "Граждане"
    context_object_name = "citizens"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingCitizen.objects.filter(subsystem=sub).annotate(
            case_count=Count("cases")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(last_name__icontains=q)
                | Q(first_name__icontains=q)
                | Q(snils__icontains=q)
            )
        if self.request.GET.get("has_cases") == "1":
            qs = qs.filter(case_count__gt=0)
        return qs.order_by("last_name", "first_name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "citizens"
        ctx["bulk_status_choices"] = []
        ctx["filter_has_cases"] = self.request.GET.get("has_cases", "")
        return ctx


class UzhvCitizenModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        citizen = get_object_or_404(HousingCitizen, pk=pk, subsystem=sub)
        cases = citizen.cases.all()[:10]
        contracts = citizen.contracts.select_related("premise").order_by("-signed_at")[:5]
        from delayu.services.uzhv_timeline import build_citizen_timeline

        return render(
            request,
            "platform/uzhv/_citizen_modal.html",
            {
                "citizen": citizen,
                "cases": cases,
                "contracts": contracts,
                "can_change": _can(request.user, "change"),
                "can_create_case": _can(request.user, "create"),
                "can_create_appeal": user_can(request.user, "M24", "create"),
                "appeals_count": citizen.appeals.count(),
                "timeline": build_citizen_timeline(citizen, request=request),
            },
        )


class UzhvCitizenCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/citizen_form.html"
    page_title = "Новый гражданин"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.setdefault("form", HousingCitizenForm())
        if "form" in kwargs:
            ctx["form"] = kwargs["form"]
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingCitizenForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            messages.success(request, f"Гражданин {obj.full_name} добавлен")
            return redirect("uzhv-citizens")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvAppealsListView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    module_code = "M24"
    template_name = "platform/uzhv/appeals_list.html"
    page_title = "Обращения граждан"
    paginate_by = 25

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        get_params = self.request.GET.copy()
        if (
            get_params.get("assignee") == "me"
            and self.request.user.is_authenticated
        ):
            get_params["assignee"] = str(self.request.user.pk)
        qs = filter_appeals(sub, params=get_params)
        page = self.request.GET.get("page", "1")
        paginator = Paginator(qs, self.paginate_by)
        ctx["page_obj"] = paginator.get_page(page)
        ctx["appeals"] = ctx["page_obj"]
        ctx["status_choices"] = HousingAppeal.Status.choices
        ctx["can_create"] = user_can(self.request.user, "M24", "create")
        ctx["can_change"] = user_can(self.request.user, "M24", "change")
        ctx["filter_overdue"] = self.request.GET.get("overdue", "")
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "appeals"
        ctx["bulk_status_choices"] = HousingAppeal.Status.choices
        from delayu.services.uzhv_bulk import subsystem_assignees

        ctx["bulk_show_assignee"] = True
        ctx["bulk_assignee_users"] = subsystem_assignees(sub)
        ctx["appeal_assignee_users"] = ctx["bulk_assignee_users"]
        return ctx


class UzhvAppealModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    module_code = "M24"

    def get(self, request, pk):
        sub = self.get_subsystem()
        appeal = get_object_or_404(
            HousingAppeal.objects.select_related(
                "citizen",
                "housing_case",
                "correspondence",
                "outgoing_correspondence",
                "assignee",
            ),
            pk=pk,
            subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_appeal_modal.html",
            {
                "appeal": appeal,
                "can_change": user_can(request.user, "M24", "change"),
            },
        )


class UzhvBuildingModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        building = get_object_or_404(MunicipalBuilding, pk=pk, subsystem=sub)
        premises = list(building.premises.order_by("number")[:15])
        from delayu.services.uzhv_timeline import build_building_timeline

        from delayu.services.uzhv_map import building_map_point, map_center_for_points

        map_pt = building_map_point(building)
        map_points = [map_pt] if map_pt else []
        center = map_center_for_points(map_points)
        return render(
            request,
            "platform/uzhv/_building_modal.html",
            {
                "building": building,
                "premises": premises,
                "premise_total": building.premises.count(),
                "premise_free": building.premises.filter(
                    status=MunicipalPremise.Status.FREE
                ).count(),
                "can_change": _can(request.user, "change"),
                "timeline": build_building_timeline(building, request=request),
                "map_points": map_points,
                "map_points_json": json.dumps(map_points),
                "map_center_json": json.dumps([center[0], center[1]]),
            },
        )


class UzhvContractModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        contract = get_object_or_404(
            HousingContract.objects.select_related("citizen", "premise", "premise__building")
            .prefetch_related("consents"),
            pk=pk,
            subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_contract_modal.html",
            {
                "contract": contract,
                "consents": list(contract.consents.order_by("-registered_at")[:5]),
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvInspectionModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        inspection = get_object_or_404(
            HousingInspection.objects.select_related("building", "inspector"),
            pk=pk,
            subsystem=sub,
        )
        prescriptions = list(inspection.prescriptions.order_by("due_date")[:5])
        return render(
            request,
            "platform/uzhv/_inspection_modal.html",
            {
                "inspection": inspection,
                "prescriptions": prescriptions,
                "prescription_count": inspection.prescriptions.count(),
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvPrescriptionModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        prescription = get_object_or_404(
            HousingPrescription.objects.select_related("inspection", "inspection__building"),
            pk=pk,
            inspection__subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_prescription_modal.html",
            {
                "prescription": prescription,
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvCourtCaseModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        court_case = get_object_or_404(
            HousingCourtCase.objects.select_related("inspection", "prescription").prefetch_related(
                "enforcement_proceedings"
            ),
            pk=pk,
            subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_court_case_modal.html",
            {
                "court_case": court_case,
                "enforcements": list(court_case.enforcement_proceedings.order_by("-initiated_at")[:5]),
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvInteragencyModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        interagency = get_object_or_404(
            HousingInteragencyRequest.objects.select_related("citizen", "housing_case"),
            pk=pk,
            subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_interagency_modal.html",
            {
                "interagency": interagency,
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvAdminProtocolModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        protocol = get_object_or_404(
            HousingAdminProtocol.objects.select_related("inspection", "inspection__building"),
            pk=pk,
            inspection__subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_admin_protocol_modal.html",
            {
                "protocol": protocol,
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvYoungFamilyModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        record = get_object_or_404(
            YoungFamilyRecord.objects.select_related("case", "case__citizen"),
            case_id=pk,
            case__subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_young_family_modal.html",
            {
                "record": record,
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvOrphanModalView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    def get(self, request, pk):
        sub = self.get_subsystem()
        record = get_object_or_404(
            OrphanHousingRecord.objects.select_related("case", "case__citizen"),
            case_id=pk,
            case__subsystem=sub,
        )
        return render(
            request,
            "platform/uzhv/_orphan_modal.html",
            {
                "record": record,
                "can_change": _can(request.user, "change"),
            },
        )


class UzhvAppealCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    module_code = "M24"
    template_name = "platform/uzhv/appeal_form.html"
    page_title = "Регистрация обращения"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        ctx.setdefault(
            "form",
            HousingAppealRegisterForm(
                subsystem=sub,
                initial={"received_at": timezone.now().date()},
            ),
        )
        ctx["sla_days"] = HousingAppeal.SLA_DAYS
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingAppealRegisterForm(request.POST, subsystem=sub)
        if form.is_valid():
            data = form.cleaned_data
            appeal = register_housing_appeal(
                subsystem=sub,
                user=request.user,
                subject=data["subject"],
                body=data.get("body") or "",
                citizen=data.get("citizen"),
                housing_case=data.get("housing_case"),
                assignee=data.get("assignee"),
                received_at=data["received_at"],
            )
            messages.success(
                request,
                f"Обращение {appeal.appeal_number} зарегистрировано. "
                f"Срок ответа: {appeal.due_date:%d.%m.%Y}",
            )
            return redirect("uzhv-appeals")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvAppealUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    module_code = "M24"
    template_name = "platform/uzhv/appeal_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        appeal = get_object_or_404(
            HousingAppeal.objects.select_related(
                "citizen", "housing_case", "correspondence", "outgoing_correspondence", "assignee"
            ),
            pk=self.kwargs["pk"],
            subsystem=sub,
        )
        ctx["appeal"] = appeal
        ctx["page_title"] = appeal.appeal_number
        ctx["sla_days"] = HousingAppeal.SLA_DAYS
        ctx["form"] = kwargs.get("form", HousingAppealForm(instance=appeal, subsystem=sub))
        ctx["attachments"] = appeal.attachments.select_related("uploaded_by").all()
        ctx["attachment_form"] = kwargs.get("attachment_form", HousingAppealAttachmentForm())
        ctx["status_history"] = appeal.status_history.select_related("changed_by").all()[:20]
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        appeal = get_object_or_404(HousingAppeal, pk=pk, subsystem=sub)
        action = request.POST.get("action", "save")

        if action == "attachment":
            form = HousingAppealAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                att = form.save(commit=False)
                att.appeal = appeal
                att.uploaded_by = request.user
                att.save()
                messages.success(request, "Вложение добавлено")
            else:
                messages.error(request, "Проверьте данные вложения")
            return redirect("uzhv-appeal-edit", pk=appeal.pk)

        if action == "delete_attachment":
            att_id = request.POST.get("attachment_id")
            if att_id:
                appeal.attachments.filter(pk=att_id).delete()
                messages.success(request, "Вложение удалено")
            return redirect("uzhv-appeal-edit", pk=appeal.pk)

        old_status = appeal.status
        form = HousingAppealForm(request.POST, instance=appeal, subsystem=sub)
        if form.is_valid():
            obj = form.save()
            from delayu.services.uzhv_appeal_status import record_appeal_status_change

            record_appeal_status_change(
                obj, old_status=old_status, new_status=obj.status, user=request.user
            )
            if obj.status in (HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED):
                if not obj.answered_at:
                    obj.answered_at = timezone.now().date()
                    obj.save(update_fields=["answered_at"])
                from delayu.services.uzhv_appeals import register_appeal_outgoing

                outgoing = register_appeal_outgoing(obj, user=request.user)
                if obj.correspondence_id:
                    from delayu.models import Correspondence

                    obj.correspondence.status = Correspondence.Status.CLOSED
                    obj.correspondence.save(update_fields=["status"])
                messages.success(
                    request,
                    f"Обращение сохранено. Исходящий ответ: {outgoing.reg_number}",
                )
            else:
                messages.success(request, "Обращение сохранено")
            return redirect("uzhv-appeals")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "appeal": appeal}
        )


class UzhvFundListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/fund_list.html"
    page_title = "Жилфонд"
    context_object_name = "buildings"
    paginate_by = 20

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            MunicipalBuilding.objects.filter(subsystem=sub)
            .annotate(
                premise_count=Count("premises"),
                free_count=Count(
                    "premises",
                    filter=Q(premises__status=MunicipalPremise.Status.FREE),
                ),
            )
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(address__icontains=q) | Q(cadastral_number__icontains=q)
            )
        condition = self.request.GET.get("condition")
        if condition in dict(MunicipalBuilding.Condition.choices):
            qs = qs.filter(condition=condition)
        if self.request.GET.get("resettlement") == "1":
            qs = qs.filter(in_resettlement_program=True)
        if self.request.GET.get("free") == "1":
            qs = qs.filter(free_count__gt=0)
        return qs.order_by("address")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["condition_choices"] = MunicipalBuilding.Condition.choices
        ctx["filter_condition"] = self.request.GET.get("condition", "")
        ctx["filter_resettlement"] = self.request.GET.get("resettlement", "")
        ctx["filter_free"] = self.request.GET.get("free", "")
        return ctx


class UzhvFundMapView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/fund_map.html"
    page_title = "Карта жилфонда"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        from delayu.services.uzhv_map import (
            buildings_for_map,
            map_center_for_points,
            map_points_for_uzhv,
        )

        building_pts = buildings_for_map(sub)
        include_geo = user_can(self.request.user, "M67", "view")
        all_pts = map_points_for_uzhv(sub, include_geo_objects=include_geo)
        center = map_center_for_points(all_pts)
        ctx["map_points_json"] = json.dumps(all_pts)
        ctx["map_center_json"] = json.dumps([center[0], center[1]])
        ctx["building_count"] = len(building_pts)
        ctx["geo_count"] = max(0, len(all_pts) - len(building_pts))
        ctx["buildings_with_coords"] = (
            MunicipalBuilding.objects.filter(subsystem=sub)
            .exclude(latitude__isnull=True)
            .exclude(longitude__isnull=True)
            .order_by("address")[:80]
        )
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_gis"] = user_can(self.request.user, "M67", "view")
        return ctx


class UzhvBuildingCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/building_form.html"
    page_title = "Новый МКД"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        ctx["form"] = MunicipalBuildingForm()
        ctx["building"] = None
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = MunicipalBuildingForm(request.POST)
        if form.is_valid():
            building = form.save(commit=False)
            building.subsystem = sub
            building.save()
            messages.success(request, "МКД добавлен")
            return redirect("uzhv-building-detail", pk=building.pk)
        return self.render_to_response({**self.get_context_data(), "form": form})


class UzhvBuildingUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/building_form.html"
    page_title = "Редактирование МКД"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        building = get_object_or_404(MunicipalBuilding, pk=self.kwargs["pk"], subsystem=sub)
        ctx["building"] = building
        ctx["form"] = MunicipalBuildingForm(instance=building)
        ctx["page_title"] = building.address
        from delayu.services.uzhv_map import building_map_point, map_center_for_points

        map_pt = building_map_point(building)
        map_points = [map_pt] if map_pt else []
        center = map_center_for_points(map_points)
        ctx["map_points"] = map_points
        ctx["map_points_json"] = json.dumps(map_points)
        ctx["map_center_json"] = json.dumps([center[0], center[1]])
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        building = get_object_or_404(MunicipalBuilding, pk=pk, subsystem=sub)
        form = MunicipalBuildingForm(request.POST, instance=building)
        if form.is_valid():
            form.save()
            messages.success(request, "МКД сохранён")
            return redirect("uzhv-building-detail", pk=building.pk)
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "building": building}
        )


class UzhvBuildingDetailView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/building_detail.html"
    page_title = "МКД"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        building = get_object_or_404(MunicipalBuilding, pk=self.kwargs["pk"], subsystem=sub)
        ctx["building"] = building
        ctx["page_title"] = building.address
        ctx["premises"] = building.premises.select_related("personal_account").order_by("number")
        ctx["premise_form"] = MunicipalPremiseForm()
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        from delayu.services.uzhv_map import building_map_point, map_center_for_points

        map_pt = building_map_point(building)
        map_points = [map_pt] if map_pt else []
        center = map_center_for_points(map_points)
        ctx["map_points"] = map_points
        ctx["map_points_json"] = json.dumps(map_points)
        ctx["map_center_json"] = json.dumps([center[0], center[1]])
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        building = get_object_or_404(MunicipalBuilding, pk=pk, subsystem=sub)
        if not _can(request.user, "create"):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        form = MunicipalPremiseForm(request.POST)
        if form.is_valid():
            premise = form.save(commit=False)
            premise.building = building
            premise.save()
            messages.success(request, f"Помещение {premise.number} добавлено")
        else:
            messages.error(request, "Проверьте данные помещения")
        return redirect("uzhv-building-detail", pk=building.pk)


class UzhvPremiseUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/premise_form.html"
    page_title = "Помещение"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        premise = get_object_or_404(
            MunicipalPremise.objects.select_related("building"),
            pk=self.kwargs["pk"],
            building__subsystem=sub,
        )
        ctx["premise"] = premise
        ctx["building"] = premise.building
        ctx["form"] = MunicipalPremiseForm(instance=premise)
        ctx["page_title"] = str(premise)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        premise = get_object_or_404(
            MunicipalPremise.objects.select_related("building"),
            pk=pk,
            building__subsystem=sub,
        )
        form = MunicipalPremiseForm(request.POST, instance=premise)
        if form.is_valid():
            form.save()
            messages.success(request, "Помещение сохранено")
            return redirect("uzhv-building-detail", pk=premise.building_id)
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "premise": premise, "building": premise.building}
        )


class UzhvResettlementListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/resettlement_list.html"
    page_title = "Расселение аварийного фонда"
    context_object_name = "buildings"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        return (
            MunicipalBuilding.objects.filter(subsystem=sub)
            .filter(
                Q(in_resettlement_program=True)
                | Q(condition=MunicipalBuilding.Condition.EMERGENCY)
                | Q(condition=MunicipalBuilding.Condition.RENOVATION)
            )
            .order_by("address")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        return ctx


class UzhvUnfitPremisesListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/unfit_premises_list.html"
    page_title = "Непригодные помещения"
    context_object_name = "premises"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        return (
            MunicipalPremise.objects.filter(building__subsystem=sub, unfit_for_living=True)
            .select_related("building")
            .order_by("building__address", "number")
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        return ctx


class UzhvReconstructionListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/reconstruction_list.html"
    page_title = "Зоны реконструкции"
    context_object_name = "buildings"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = MunicipalBuilding.objects.filter(
            subsystem=sub, in_reconstruction_zone=True
        ).order_by("address")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(address__icontains=q) | Q(reconstruction_program__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        return ctx


class UzhvPersonalAccountsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/personal_accounts_list.html"
    page_title = "Лицевые счета"
    context_object_name = "accounts"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            HousingPersonalAccount.objects.filter(subsystem=sub)
            .select_related("premise", "premise__building", "tenant_citizen")
            .order_by("account_number")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(account_number__icontains=q)
                | Q(premise__building__address__icontains=q)
                | Q(tenant_citizen__last_name__icontains=q)
            )
        if self.request.GET.get("active") == "1":
            qs = qs.filter(is_active=True)
        elif self.request.GET.get("active") == "0":
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["filter_active"] = self.request.GET.get("active", "")
        return ctx


class UzhvPersonalAccountEditView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/personal_account_form.html"
    required_action = "change"

    def _premise(self):
        sub = self.get_subsystem()
        return get_object_or_404(
            MunicipalPremise.objects.select_related("building", "personal_account"),
            pk=self.kwargs["premise_pk"],
            building__subsystem=sub,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        premise = self._premise()
        account = ensure_personal_account(premise, user=self.request.user)
        sub = self.get_subsystem()
        ctx["premise"] = premise
        ctx["building"] = premise.building
        ctx["account"] = account
        ctx["page_title"] = f"ЛС {account.account_number}"
        ctx["form"] = kwargs.get(
            "form",
            HousingPersonalAccountForm(instance=account, subsystem=sub),
        )
        ctx["members"] = account.members.order_by("sort_order", "full_name")
        ctx["history"] = account.history.select_related("changed_by").order_by("-changed_at")[:20]
        ctx["member_form"] = kwargs.get("member_form", HousingPersonalAccountMemberForm())
        return ctx

    def post(self, request, premise_pk):
        premise = self._premise()
        account = ensure_personal_account(premise, user=request.user)
        sub = self.get_subsystem()
        action = request.POST.get("action", "save")

        if action == "delete_member":
            mid = request.POST.get("member_id")
            if mid and mid.isdigit():
                HousingPersonalAccountMember.objects.filter(pk=int(mid), account=account).delete()
                record_account_history(account, "Удалён член семьи из состава ЛС", request.user)
                messages.success(request, "Запись удалена")
            return redirect("uzhv-personal-account-edit", premise_pk=premise_pk)

        if action == "add_member":
            form = HousingPersonalAccountMemberForm(request.POST)
            if form.is_valid():
                member = form.save(commit=False)
                member.account = account
                member.save()
                record_account_history(
                    account, f"Добавлен в состав: {member.full_name}", request.user
                )
                messages.success(request, "Член семьи добавлен")
                return redirect("uzhv-personal-account-edit", premise_pk=premise_pk)
            return self.render_to_response(self.get_context_data(member_form=form))

        form = HousingPersonalAccountForm(request.POST, instance=account, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            record_account_history(account, "Обновлены сведения лицевого счёта", request.user)
            messages.success(request, "Лицевой счёт сохранён")
            return redirect("uzhv-personal-account-edit", premise_pk=premise_pk)
        return self.render_to_response(self.get_context_data(form=form))


class UzhvPersonalAccountExtractView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    required_action = "view"

    def get(self, request, pk):
        sub = self.get_subsystem()
        account = get_object_or_404(
            HousingPersonalAccount.objects.select_related(
                "premise", "premise__building", "tenant_citizen"
            ).prefetch_related("members", "history"),
            pk=pk,
            subsystem=sub,
        )
        try:
            title, text = render_personal_account_document(account)
        except KeyError:
            from django.http import Http404

            raise Http404("Шаблон не найден") from None
        data = text_to_docx_bytes(title, text)
        resp = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = f'attachment; filename="extract-{account.account_number}.docx"'
        return resp


class UzhvPrivatePremisesListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/private_premises_list.html"
    page_title = "Частный фонд"
    context_object_name = "premises"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = PrivateManagedPremise.objects.filter(subsystem=sub).order_by("address", "premise_number")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(address__icontains=q)
                | Q(owner_name__icontains=q)
                | Q(cadastral_number__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["can_create"] = _can(self.request.user, "create")
        return ctx


class UzhvPrivatePremiseCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/private_premise_form.html"
    page_title = "Новое помещение частного фонда"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["form"] = kwargs.get("form", PrivateManagedPremiseForm())
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = PrivateManagedPremiseForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            messages.success(request, "Помещение добавлено")
            return redirect("uzhv-private-premises")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvPrivatePremiseUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/private_premise_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        premise = get_object_or_404(PrivateManagedPremise, pk=self.kwargs["pk"], subsystem=sub)
        ctx["premise"] = premise
        ctx["page_title"] = str(premise)
        ctx["form"] = PrivateManagedPremiseForm(instance=premise)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        premise = get_object_or_404(PrivateManagedPremise, pk=pk, subsystem=sub)
        form = PrivateManagedPremiseForm(request.POST, instance=premise)
        if form.is_valid():
            form.save()
            messages.success(request, "Сохранено")
            return redirect("uzhv-private-premises")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "premise": premise}
        )


class UzhvInspectionsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/inspections_list.html"
    page_title = "Жилищный контроль"
    context_object_name = "inspections"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingInspection.objects.filter(subsystem=sub).select_related(
            "building", "inspector"
        )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(inspection_number__icontains=q)
                | Q(check_subject__icontains=q)
                | Q(counterparty_name__icontains=q)
                | Q(building__address__icontains=q)
            )
        return qs.order_by("-planned_date", "-inspection_number")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = HousingInspection.Status.choices
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "inspections"
        ctx["bulk_status_choices"] = HousingInspection.Status.choices
        return ctx


class UzhvInspectionPlansListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/inspection_plans_list.html"
    page_title = "Планы внеплановых проверок"
    context_object_name = "plans"
    paginate_by = 20

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            HousingInspectionPlan.objects.filter(subsystem=sub)
            .select_related("created_by")
            .annotate(inspection_count=Count("inspections"))
            .order_by("-period_from")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(plan_number__icontains=q) | Q(title__icontains=q))
        status = self.request.GET.get("status")
        if status in dict(HousingInspectionPlan.Status.choices):
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["status_choices"] = HousingInspectionPlan.Status.choices
        return ctx


class UzhvInspectionPlanCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_plan_form.html"
    page_title = "Новый план проверок"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        today = timezone.now().date()
        ctx["form"] = kwargs.get(
            "form",
            HousingInspectionPlanForm(
                initial={
                    "plan_number": next_inspection_plan_number(sub),
                    "period_from": today,
                    "period_to": today + timedelta(days=90),
                }
            ),
        )
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingInspectionPlanForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.created_by = request.user
            if obj.status == HousingInspectionPlan.Status.APPROVED and not obj.approved_at:
                obj.approved_at = timezone.now().date()
            obj.save()
            messages.success(request, f"План {obj.plan_number} создан")
            return redirect("uzhv-inspection-plan-detail", pk=obj.pk)
        return self.render_to_response(self.get_context_data(form=form))


class UzhvInspectionPlanDetailView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_plan_detail.html"
    page_title = "План проверок"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        plan = get_object_or_404(
            HousingInspectionPlan.objects.select_related("created_by"),
            pk=self.kwargs["pk"],
            subsystem=sub,
        )
        ctx["plan"] = plan
        ctx["page_title"] = plan.plan_number
        ctx["inspections"] = plan.inspections.select_related("building", "inspector").order_by(
            "-planned_date"
        )
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["can_create"] = _can(self.request.user, "create")
        return ctx


class UzhvInspectionPlanUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_plan_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        plan = get_object_or_404(HousingInspectionPlan, pk=self.kwargs["pk"], subsystem=sub)
        ctx["plan"] = plan
        ctx["page_title"] = f"План {plan.plan_number}"
        ctx["form"] = HousingInspectionPlanForm(instance=plan)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        plan = get_object_or_404(HousingInspectionPlan, pk=pk, subsystem=sub)
        form = HousingInspectionPlanForm(request.POST, instance=plan)
        if form.is_valid():
            obj = form.save(commit=False)
            if obj.status == HousingInspectionPlan.Status.APPROVED and not obj.approved_at:
                obj.approved_at = timezone.now().date()
            obj.save()
            messages.success(request, "План сохранён")
            return redirect("uzhv-inspection-plan-detail", pk=obj.pk)
        return self.render_to_response({**self.get_context_data(), "form": form, "plan": plan})


class UzhvInspectionOrdersListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/inspection_orders_list.html"
    page_title = "Предписания на проведение проверок"
    context_object_name = "orders"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingInspectionOrder.objects.filter(subsystem=sub).select_related(
            "building", "plan", "inspection"
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(order_number__icontains=q)
                | Q(addressee__icontains=q)
                | Q(check_subject__icontains=q)
            )
        status = self.request.GET.get("status")
        if status in dict(HousingInspectionOrder.Status.choices):
            qs = qs.filter(status=status)
        if self.request.GET.get("overdue") == "1":
            today = timezone.now().date()
            qs = qs.exclude(
                status__in=[
                    HousingInspectionOrder.Status.COMPLETED,
                    HousingInspectionOrder.Status.CANCELLED,
                ]
            ).filter(conduct_by__lt=today)
        return qs.order_by("-issued_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["status_choices"] = HousingInspectionOrder.Status.choices
        ctx["filter_overdue"] = self.request.GET.get("overdue", "")
        return ctx


class UzhvInspectionOrderCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_order_form.html"
    page_title = "Новое предписание на проверку"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {
            "order_number": next_inspection_order_number(sub),
            "issued_at": timezone.now().date(),
            "conduct_by": timezone.now().date() + timedelta(days=14),
        }
        plan_id = self.request.GET.get("plan")
        if plan_id and plan_id.isdigit():
            plan = HousingInspectionPlan.objects.filter(pk=int(plan_id), subsystem=sub).first()
            if plan:
                initial["plan"] = plan.pk
        ctx["form"] = kwargs.get("form", HousingInspectionOrderForm(initial=initial, subsystem=sub))
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingInspectionOrderForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            messages.success(request, f"Предписание {obj.order_number} зарегистрировано")
            return redirect("uzhv-inspection-orders")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvInspectionOrderUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_order_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        order = get_object_or_404(HousingInspectionOrder, pk=self.kwargs["pk"], subsystem=sub)
        ctx["order"] = order
        ctx["page_title"] = order.order_number
        ctx["form"] = HousingInspectionOrderForm(instance=order, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        order = get_object_or_404(HousingInspectionOrder, pk=pk, subsystem=sub)
        action = request.POST.get("action", "save")
        if action == "spawn_inspection" and not order.inspection_id:
            inspection = spawn_inspection_from_order(order)
            messages.success(request, f"Создана проверка {inspection.inspection_number}")
            return redirect("uzhv-inspection-edit", pk=inspection.pk)
        form = HousingInspectionOrderForm(request.POST, instance=order, subsystem=sub)
        if form.is_valid():
            obj = form.save()
            if (
                obj.inspection_id
                and obj.inspection.status == HousingInspection.Status.COMPLETED
                and obj.status != HousingInspectionOrder.Status.COMPLETED
            ):
                obj.status = HousingInspectionOrder.Status.COMPLETED
                obj.save(update_fields=["status", "updated_at"])
            messages.success(request, "Сохранено")
            return redirect("uzhv-inspection-orders")
        return self.render_to_response({**self.get_context_data(), "form": form, "order": order})


class UzhvInspectionCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_form.html"
    page_title = "Новая проверка"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {"inspection_number": next_inspection_number(sub)}
        plan_id = self.request.GET.get("plan")
        if plan_id and plan_id.isdigit():
            plan = HousingInspectionPlan.objects.filter(pk=int(plan_id), subsystem=sub).first()
            if plan:
                initial["plan"] = plan.pk
                initial["inspection_type"] = HousingInspection.InspectionType.UNPLANNED
        building_id = self.request.GET.get("building")
        if building_id and building_id.isdigit():
            building = MunicipalBuilding.objects.filter(pk=int(building_id), subsystem=sub).first()
            if building:
                initial["building"] = building.pk
                initial["object_type"] = HousingInspection.ObjectType.MKD
        ctx["form"] = HousingInspectionForm(initial=initial, subsystem=sub)
        ctx["inspection"] = None
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingInspectionForm(request.POST, subsystem=sub)
        if form.is_valid():
            inspection = form.save(commit=False)
            inspection.subsystem = sub
            inspection.save()
            messages.success(request, "Проверка зарегистрирована")
            return redirect("uzhv-inspection-edit", pk=inspection.pk)
        return self.render_to_response({**self.get_context_data(), "form": form})


class UzhvInspectionUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/inspection_form.html"
    page_title = "Проверка"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        inspection = get_object_or_404(
            HousingInspection.objects.select_related("building", "inspector"),
            pk=self.kwargs["pk"],
            subsystem=sub,
        )
        ctx["inspection"] = inspection
        ctx["page_title"] = inspection.inspection_number
        ctx["form"] = HousingInspectionForm(instance=inspection, subsystem=sub)
        ctx["prescriptions"] = inspection.prescriptions.all()
        ctx["prescription_form"] = HousingPrescriptionForm(
            initial={"issued_at": timezone.now().date()}
        )
        ctx["admin_protocols"] = inspection.admin_protocols.all()
        ctx["protocol_form"] = HousingAdminProtocolForm(
            initial={"protocol_date": timezone.now().date()}
        )
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        inspection = get_object_or_404(HousingInspection, pk=pk, subsystem=sub)
        if request.POST.get("form_type") == "prescription":
            pform = HousingPrescriptionForm(request.POST)
            if pform.is_valid():
                prescription = pform.save(commit=False)
                prescription.inspection = inspection
                prescription.save()
                if prescription.is_overdue:
                    prescription.status = HousingPrescription.Status.OVERDUE
                    prescription.save(update_fields=["status"])
                inspection.violations_found = True
                inspection.save(update_fields=["violations_found"])
                messages.success(request, "Предписание добавлено")
            else:
                messages.error(request, "Проверьте данные предписания")
            return redirect("uzhv-inspection-edit", pk=inspection.pk)
        if request.POST.get("form_type") == "protocol":
            pform = HousingAdminProtocolForm(request.POST)
            if pform.is_valid():
                protocol = pform.save(commit=False)
                protocol.inspection = inspection
                protocol.save()
                inspection.violations_found = True
                inspection.save(update_fields=["violations_found"])
                messages.success(request, "Протокол об АП добавлен")
            else:
                messages.error(request, "Проверьте данные протокола")
            return redirect("uzhv-inspection-edit", pk=inspection.pk)
        form = HousingInspectionForm(request.POST, instance=inspection, subsystem=sub)
        if form.is_valid():
            old_status = inspection.status
            obj = form.save()
            if (
                obj.status == HousingInspection.Status.COMPLETED
                and old_status != HousingInspection.Status.COMPLETED
            ):
                complete_inspection_order_for_inspection(obj)
            messages.success(request, "Проверка сохранена")
            return redirect("uzhv-inspections")
        ctx = self.get_context_data()
        ctx["form"] = form
        ctx["prescription_form"] = HousingPrescriptionForm(
            initial={"issued_at": timezone.now().date()}
        )
        ctx["protocol_form"] = HousingAdminProtocolForm(
            initial={"protocol_date": timezone.now().date()}
        )
        return self.render_to_response(ctx)


class UzhvContractsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/contracts_list.html"
    page_title = "Договоры"
    context_object_name = "contracts"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            HousingContract.objects.filter(subsystem=sub)
            .select_related("citizen", "premise", "premise__building")
            .order_by("-signed_at")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(contract_number__icontains=q)
                | Q(citizen__last_name__icontains=q)
                | Q(citizen__first_name__icontains=q)
                | Q(premise__building__address__icontains=q)
            )
        active = self.request.GET.get("active")
        if active == "1":
            qs = qs.filter(is_active=True)
        elif active == "0":
            qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "contracts"
        ctx["bulk_status_choices"] = []
        ctx["bulk_allow_close"] = True
        ctx["filter_active"] = self.request.GET.get("active", "")
        return ctx


class UzhvLowIncomeView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/low_income.html"
    page_title = "Расчёт малоимущих"
    required_action = "change"

    def _case(self):
        sub = self.get_subsystem()
        return get_object_or_404(
            HousingQueueCase.objects.select_related("citizen"),
            pk=self.kwargs["pk"],
            subsystem=sub,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        case = self._case()
        ctx["case"] = case
        ctx["citizen"] = case.citizen
        from delayu.services.uzhv_bulk import subsystem_assignees

        ctx["assignee_users"] = subsystem_assignees(sub)
        ctx["subsistence_minimum"] = get_subsistence_minimum(sub)
        ctx["member_formset"] = kwargs.get(
            "member_formset",
            HousingHouseholdMemberFormSet(instance=case),
        )
        ctx["document_codes"] = [
            ("uzhv_low_income_conclusion", "Заключение о малоимущих"),
            ("uzhv_queue_certificate", "Справка о постановке на учёт"),
            ("uzhv_account_decision", "Решение о постановке / отказе"),
        ]
        ctx["attachments"] = case.attachments.select_related("uploaded_by").all()
        ctx["attachment_form"] = kwargs.get("attachment_form", HousingCaseAttachmentForm())
        ctx["review_days"] = get_low_income_review_days(sub)
        if case.low_income_review_due_at:
            today = timezone.now().date()
            ctx["review_overdue"] = (
                case.low_income_eligible is None and case.low_income_review_due_at < today
            )
            ctx["review_due_soon"] = (
                case.low_income_eligible is None
                and case.low_income_review_due_at >= today
                and case.low_income_review_due_at <= today + timedelta(days=7)
            )
        if case.per_capita_income is not None:
            ctx["last_result"] = {
                "per_capita_income": case.per_capita_income,
                "eligible": case.low_income_eligible,
                "conclusion": case.low_income_conclusion,
                "queue_position": case.queue_position,
            }
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(HousingQueueCase, pk=pk, subsystem=sub)
        action = request.POST.get("action", "calculate")

        if action == "members":
            formset = HousingHouseholdMemberFormSet(request.POST, instance=case)
            if formset.is_valid():
                formset.save()
                case.household_size = case.household_members.count() or case.household_size
                case.save(update_fields=["household_size", "updated_at"])
                messages.success(request, "Состав семьи сохранён")
            else:
                messages.error(request, "Исправьте ошибки в составе семьи")
                return self.render_to_response(self.get_context_data(member_formset=formset))
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "application":
            app_date_raw = request.POST.get("low_income_application_at")
            if app_date_raw:
                app_date = date.fromisoformat(app_date_raw)
                case.low_income_application_at = app_date
                case.low_income_review_due_at = compute_low_income_review_due(app_date, sub)
                case.save(
                    update_fields=[
                        "low_income_application_at",
                        "low_income_review_due_at",
                        "updated_at",
                    ]
                )
                messages.success(
                    request,
                    f"Заявление зарегистрировано, срок рассмотрения до "
                    f"{case.low_income_review_due_at:%d.%m.%Y}",
                )
            else:
                messages.error(request, "Укажите дату заявления")
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "upload":
            form = HousingCaseAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                att = form.save(commit=False)
                att.case = case
                att.uploaded_by = request.user
                att.save()
                messages.success(request, "Вложение загружено")
            else:
                messages.error(request, "Не удалось загрузить файл")
                return self.render_to_response(self.get_context_data(attachment_form=form))
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "delete_attachment":
            att_id = request.POST.get("attachment_id")
            if att_id:
                HousingCaseAttachment.objects.filter(pk=att_id, case=case).delete()
                messages.success(request, "Вложение удалено")
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "sync_applicant":
            sync_applicant_to_household(case)
            case.household_size = case.household_members.count() or case.household_size
            case.save(update_fields=["household_size", "updated_at"])
            messages.success(request, "Заявитель добавлен в состав семьи")
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "assign":
            from delayu.services.uzhv_bulk import subsystem_assignees

            raw = request.POST.get("assignee", "").strip()
            user_id = int(raw) if raw.isdigit() else None
            if user_id and not subsystem_assignees(sub).filter(pk=user_id).exists():
                messages.error(request, "Недопустимый исполнитель")
            else:
                case.assignee_id = user_id
                case.save(update_fields=["assignee", "updated_at"])
                messages.success(request, "Исполнитель назначен")
            return redirect("uzhv-case-low-income", pk=case.pk)

        if action == "reject":
            reject_low_income_application(case, user=request.user)
            messages.success(request, "Зафиксирован отказ, дело снято с учёта")
            return redirect("uzhv-cases")

        if action == "calculate":
            result = apply_low_income_calculation(
                case,
                subsystem=sub,
                monthly_income=request.POST.get("monthly_income") or 0,
                household_size=int(request.POST.get("household_size") or 1),
                property_value=request.POST.get("property_value") or 0,
                user=request.user,
            )
            if result["eligible"]:
                messages.success(
                    request,
                    f"Признан малоимущим. Очерёдность после пересчёта: "
                    f"{case.queue_position or '—'}",
                )
            else:
                messages.warning(request, "Критерии малоимущих не выполнены")
            return redirect("uzhv-case-low-income", pk=case.pk)

        messages.error(request, "Неизвестное действие")
        return redirect("uzhv-case-low-income", pk=case.pk)


class UzhvCaseDocumentView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    required_action = "view"

    def get(self, request, pk, code):
        case = get_object_or_404(
            HousingQueueCase.objects.select_related("citizen"),
            pk=pk,
            subsystem=self.get_subsystem(),
        )
        fmt = (request.GET.get("format") or "docx").lower()
        try:
            title, text = render_case_document(case, code)
        except KeyError:
            from django.http import Http404

            raise Http404("Шаблон не найден") from None

        if fmt == "txt":
            resp = HttpResponse(text, content_type="text/plain; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="{code}.txt"'
            return resp
        data = text_to_docx_bytes(title, text)
        resp = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = f'attachment; filename="{code}.docx"'
        return resp


class UzhvAppealDocumentView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    module_code = "M24"
    required_action = "view"

    def get(self, request, pk):
        appeal = get_object_or_404(
            HousingAppeal.objects.select_related("citizen", "housing_case", "outgoing_correspondence"),
            pk=pk,
            subsystem=self.get_subsystem(),
        )
        fmt = (request.GET.get("format") or "docx").lower()
        try:
            title, text = render_appeal_document(appeal)
        except KeyError:
            from django.http import Http404

            raise Http404("Шаблон не найден") from None
        if fmt == "txt":
            resp = HttpResponse(text, content_type="text/plain; charset=utf-8")
            resp["Content-Disposition"] = f'attachment; filename="appeal_{appeal.pk}.txt"'
            return resp
        data = text_to_docx_bytes(title, text)
        resp = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = f'attachment; filename="appeal_{appeal.pk}.docx"'
        return resp


class UzhvCaseZipView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    required_action = "view"

    def get(self, request, pk):
        case = get_object_or_404(
            HousingQueueCase.objects.select_related("citizen").prefetch_related(
                "household_members", "attachments", "appeals", "interagency_requests"
            ),
            pk=pk,
            subsystem=self.get_subsystem(),
        )
        if case.category == HousingQueueCase.Category.ORPHAN:
            data = build_orphan_package_bytes(case)
            prefix = "orphan"
        else:
            data = build_case_zip_bytes(case)
            prefix = "case"
        resp = HttpResponse(data, content_type="application/zip")
        resp["Content-Disposition"] = (
            f'attachment; filename="{prefix}_{case.case_number}.zip"'
        )
        return resp


class UzhvContractCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/contract_form.html"
    page_title = "Новый договор"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        ctx["form"] = kwargs.get(
            "form",
            HousingContractForm(
                subsystem=sub,
                initial={
                    "contract_number": next_contract_number(sub),
                    "signed_at": timezone.now().date(),
                    "is_active": True,
                },
            ),
        )
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingContractForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            save_housing_contract(obj)
            messages.success(request, f"Договор {obj.contract_number} создан")
            return redirect("uzhv-contracts")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvContractUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/contract_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        contract = get_object_or_404(HousingContract, pk=self.kwargs["pk"], subsystem=sub)
        ctx["contract"] = contract
        ctx["page_title"] = f"Договор {contract.contract_number}"
        ctx["form"] = HousingContractForm(instance=contract, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        contract = get_object_or_404(HousingContract, pk=pk, subsystem=sub)
        old_premise = contract.premise_id
        form = HousingContractForm(request.POST, instance=contract, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            save_housing_contract(obj, old_premise_id=old_premise)
            messages.success(request, "Договор сохранён")
            return redirect("uzhv-contracts")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "contract": contract}
        )


class UzhvContractConsentsView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/contract_consents.html"
    required_action = "change"

    def _contract(self):
        sub = self.get_subsystem()
        return get_object_or_404(
            HousingContract.objects.select_related("citizen", "premise", "premise__building"),
            pk=self.kwargs["pk"],
            subsystem=sub,
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        contract = self._contract()
        ctx["contract"] = contract
        ctx["page_title"] = f"Согласия — {contract.contract_number}"
        ctx["consents"] = contract.consents.select_related("created_by").order_by("-registered_at")
        ctx["attachments"] = contract.attachments.select_related("uploaded_by").order_by("-uploaded_at")
        ctx["consent_form"] = kwargs.get("consent_form", HousingContractConsentForm())
        ctx["attachment_form"] = kwargs.get("attachment_form", HousingContractAttachmentForm())
        ctx["consent_type_choices"] = HousingContractConsent.ConsentType.choices
        return ctx

    def post(self, request, pk):
        contract = self._contract()
        action = request.POST.get("action", "add_consent")

        if action == "delete_consent":
            cid = request.POST.get("consent_id")
            if cid and cid.isdigit():
                HousingContractConsent.objects.filter(pk=int(cid), contract=contract).delete()
                messages.success(request, "Запись удалена")
            return redirect("uzhv-contract-consents", pk=pk)

        if action == "delete_attachment":
            aid = request.POST.get("attachment_id")
            if aid and aid.isdigit():
                HousingContractAttachment.objects.filter(pk=int(aid), contract=contract).delete()
                messages.success(request, "Вложение удалено")
            return redirect("uzhv-contract-consents", pk=pk)

        if action == "add_attachment":
            form = HousingContractAttachmentForm(request.POST, request.FILES)
            if form.is_valid():
                att = form.save(commit=False)
                att.contract = contract
                att.uploaded_by = request.user
                att.save()
                messages.success(request, "Вложение загружено")
                return redirect("uzhv-contract-consents", pk=pk)
            return self.render_to_response(self.get_context_data(attachment_form=form))

        form = HousingContractConsentForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.contract = contract
            obj.created_by = request.user
            obj.save()
            messages.success(request, "Согласие зарегистрировано")
            return redirect("uzhv-contract-consents", pk=pk)
        return self.render_to_response(self.get_context_data(consent_form=form))


class UzhvContractConsentDocumentView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    required_action = "view"

    def get(self, request, pk, consent_pk):
        sub = self.get_subsystem()
        consent = get_object_or_404(
            HousingContractConsent.objects.select_related("contract"),
            pk=consent_pk,
            contract_id=pk,
            contract__subsystem=sub,
        )
        try:
            title, text = render_consent_document(consent)
        except KeyError:
            from django.http import Http404

            raise Http404("Шаблон не найден") from None
        data = text_to_docx_bytes(title, text)
        resp = HttpResponse(
            data,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        resp["Content-Disposition"] = f'attachment; filename="consent-{consent.pk}.docx"'
        return resp


class UzhvReportsHubView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    module_code = "M15"
    template_name = "platform/uzhv/reports.html"
    page_title = "Отчёты УЖВ"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reports"] = [
            {"code": code, "title": meta[0], "period": meta[2]}
            for code, meta in REPORT_BUILDERS.items()
        ]
        return ctx


class UzhvReportExportView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    module_code = "M15"

    def get(self, request, code, fmt="csv"):
        if code not in REPORT_BUILDERS:
            from django.http import Http404

            raise Http404
        sub = self.get_subsystem()
        period_start = period_end = None
        meta = REPORT_BUILDERS[code]
        if meta[2]:
            ps = request.GET.get("from")
            pe = request.GET.get("to")
            if ps:
                period_start = date.fromisoformat(ps)
            if pe:
                period_end = date.fromisoformat(pe)
        fmt = (fmt or "csv").lower()
        if fmt not in ("csv", "xlsx", "pdf"):
            from django.http import Http404

            raise Http404
        return http_export_report(
            code=code,
            subsystem=sub,
            fmt=fmt,
            period_start=period_start,
            period_end=period_end,
        )


class UzhvYoungFamiliesListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/young_families_list.html"
    page_title = "Молодые семьи"
    context_object_name = "records"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            YoungFamilyRecord.objects.filter(case__subsystem=sub)
            .select_related("case", "case__citizen", "case__assignee")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(case__case_number__icontains=q)
                | Q(case__citizen__last_name__icontains=q)
                | Q(case__citizen__first_name__icontains=q)
                | Q(spouse_last_name__icontains=q)
            )
        program = self.request.GET.get("program")
        if program in dict(YoungFamilyRecord.Program.choices):
            qs = qs.filter(program=program)
        if self.request.GET.get("meets") == "1":
            qs = qs.filter(meets_criteria=True)
        elif self.request.GET.get("meets") == "0":
            qs = qs.filter(meets_criteria=False)
        return qs.order_by("-case__registered_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "young_families"
        ctx["bulk_status_choices"] = []
        ctx["bulk_show_meets"] = True
        ctx["bulk_program_choices"] = YoungFamilyRecord.Program.choices
        ctx["program_choices"] = YoungFamilyRecord.Program.choices
        ctx["filter_program"] = self.request.GET.get("program", "")
        ctx["filter_meets"] = self.request.GET.get("meets", "")
        return ctx


class UzhvYoungFamilyEditView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/young_family_form.html"
    page_title = "Молодая семья"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase,
            pk=self.kwargs["pk"],
            subsystem=sub,
            category=HousingQueueCase.Category.YOUNG_FAMILY,
        )
        record, _ = YoungFamilyRecord.objects.get_or_create(case=case)
        ctx["case"] = case
        ctx["record"] = record
        ctx["program_choices"] = YoungFamilyRecord.Program.choices
        ctx["document_codes"] = [
            ("uzhv_young_family_certificate", "Справка для списка"),
        ]
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase,
            pk=pk,
            subsystem=sub,
            category=HousingQueueCase.Category.YOUNG_FAMILY,
        )
        record, _ = YoungFamilyRecord.objects.get_or_create(case=case)
        action = request.POST.get("action", "save")
        if action == "check_criteria":
            from delayu.services.uzhv_young_family import check_young_family_criteria

            result = check_young_family_criteria(record)
            record.meets_criteria = result.meets
            record.criteria_notes = result.notes
            record.criteria_checked_at = timezone.now()
            record.save(
                update_fields=["meets_criteria", "criteria_notes", "criteria_checked_at"]
            )
            messages.success(request, result.notes)
            return redirect("uzhv-young-family-edit", pk=case.pk)

        record.spouse_last_name = request.POST.get("spouse_last_name", "")
        record.spouse_first_name = request.POST.get("spouse_first_name", "")
        record.spouse_middle_name = request.POST.get("spouse_middle_name", "")
        record.children_count = int(request.POST.get("children_count") or 0)
        record.program = request.POST.get("program") or YoungFamilyRecord.Program.JSK
        record.meets_criteria = request.POST.get("meets_criteria") == "1"
        record.notes = request.POST.get("notes", "")
        md = request.POST.get("marriage_date")
        if md:
            record.marriage_date = date.fromisoformat(md)
        sbd = request.POST.get("spouse_birth_date")
        record.spouse_birth_date = date.fromisoformat(sbd) if sbd else None
        record.save()
        messages.success(request, "Данные молодой семьи сохранены")
        return redirect("uzhv-young-families")


class UzhvOrphansListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/orphans_list.html"
    page_title = "Дети-сироты"
    context_object_name = "records"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = (
            OrphanHousingRecord.objects.filter(case__subsystem=sub)
            .select_related("case", "case__citizen", "case__assignee")
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(case__case_number__icontains=q)
                | Q(case__citizen__last_name__icontains=q)
                | Q(mintrud_decision_number__icontains=q)
            )
        status = self.request.GET.get("status")
        if status in dict(OrphanHousingRecord.HousingStatus.choices):
            qs = qs.filter(housing_status=status)
        if self.request.GET.get("has_decision") == "1":
            qs = qs.filter(mintrud_decision_date__isnull=False)
        return qs.order_by("-case__registered_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "orphans"
        ctx["bulk_status_choices"] = OrphanHousingRecord.HousingStatus.choices
        ctx["status_choices"] = OrphanHousingRecord.HousingStatus.choices
        ctx["filter_status"] = self.request.GET.get("status", "")
        ctx["filter_has_decision"] = self.request.GET.get("has_decision", "")
        return ctx


class UzhvOrphanEditView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/orphan_form.html"
    page_title = "Дети-сироты"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase,
            pk=self.kwargs["pk"],
            subsystem=sub,
            category=HousingQueueCase.Category.ORPHAN,
        )
        record, _ = OrphanHousingRecord.objects.get_or_create(case=case)
        ctx["case"] = case
        ctx["record"] = record
        ctx["status_choices"] = OrphanHousingRecord.HousingStatus.choices
        ctx["premise_choices"] = MunicipalPremise.objects.filter(
            building__subsystem=sub, specialized_orphan=True
        ).select_related("building")
        ctx["document_codes"] = [
            ("uzhv_orphan_resolution_draft", "Проект постановления"),
            ("uzhv_orphan_package_cover", "Сопроводительный лист"),
        ]
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        case = get_object_or_404(
            HousingQueueCase,
            pk=pk,
            subsystem=sub,
            category=HousingQueueCase.Category.ORPHAN,
        )
        record, _ = OrphanHousingRecord.objects.get_or_create(case=case)
        record.mintrud_decision_number = request.POST.get("mintrud_decision_number", "")
        record.housing_status = request.POST.get("housing_status") or record.housing_status
        record.notes = request.POST.get("notes", "")
        dd = request.POST.get("mintrud_decision_date")
        record.mintrud_decision_date = date.fromisoformat(dd) if dd else None
        premise_id = request.POST.get("assigned_premise")
        record.assigned_premise_id = int(premise_id) if premise_id else None
        record.save()
        messages.success(request, "Дело дети-сироты сохранено")
        return redirect("uzhv-orphans")


class UzhvContractImportView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/contract_import.html"
    page_title = "Импорт договоров"
    required_action = "create"

    def post(self, request):
        sub = self.get_subsystem()
        f = request.FILES.get("file")
        if not f:
            messages.error(request, "Выберите файл xlsx")
            return redirect("uzhv-contract-import")
        result = import_contracts_xlsx(sub, f)
        if result.errors:
            for e in result.errors:
                messages.error(request, e)
        else:
            messages.success(
                request,
                f"Импорт завершён: создано {result.created}, пропущено/обновлено {result.skipped}",
            )
        return redirect("uzhv-contracts")


class UzhvPrescriptionsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/prescriptions_list.html"
    page_title = "Предписания об устранении"
    context_object_name = "prescriptions"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        sync_overdue_prescriptions(sub)
        from delayu.services.uzhv_overdue import (
            filter_prescriptions_assignee,
            parse_hub_assignee_filter,
        )

        assignee_id = parse_hub_assignee_filter(self.request.GET, self.request.user)
        qs = HousingPrescription.objects.filter(inspection__subsystem=sub).select_related(
            "inspection", "inspection__building", "inspection__inspector"
        )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        if self.request.GET.get("overdue") == "1":
            today = timezone.now().date()
            qs = qs.exclude(
                status__in=[
                    HousingPrescription.Status.FULFILLED,
                    HousingPrescription.Status.CANCELLED,
                ]
            ).filter(due_date__lt=today)
        qs = filter_prescriptions_assignee(qs, assignee_id)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(prescription_number__icontains=q)
                | Q(description__icontains=q)
                | Q(inspection__inspection_number__icontains=q)
            )
        return qs.order_by("due_date", "prescription_number")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from delayu.services.uzhv_bulk import subsystem_assignees

        ctx["status_choices"] = HousingPrescription.Status.choices
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["filter_overdue"] = self.request.GET.get("overdue", "")
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        ctx["assignee_users"] = subsystem_assignees(self.get_subsystem())
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "prescriptions"
        ctx["bulk_status_choices"] = HousingPrescription.Status.choices
        return ctx


class UzhvPrescriptionUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/prescription_form.html"
    page_title = "Предписание"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        prescription = get_object_or_404(
            HousingPrescription.objects.select_related("inspection", "inspection__building"),
            pk=self.kwargs["pk"],
            inspection__subsystem=sub,
        )
        ctx["prescription"] = prescription
        ctx["page_title"] = prescription.prescription_number
        ctx["form"] = HousingPrescriptionForm(instance=prescription)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        prescription = get_object_or_404(
            HousingPrescription, pk=pk, inspection__subsystem=sub
        )
        form = HousingPrescriptionForm(request.POST, instance=prescription)
        if form.is_valid():
            obj = form.save()
            if obj.status == HousingPrescription.Status.FULFILLED and not obj.fulfilled_at:
                obj.fulfilled_at = timezone.now().date()
                obj.save(update_fields=["fulfilled_at"])
            elif obj.is_overdue and obj.status not in (
                HousingPrescription.Status.FULFILLED,
                HousingPrescription.Status.CANCELLED,
            ):
                obj.status = HousingPrescription.Status.OVERDUE
                obj.save(update_fields=["status"])
            messages.success(request, "Предписание сохранено")
            return redirect("uzhv-prescriptions")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "prescription": prescription}
        )


class UzhvCourtCasesListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/court_cases_list.html"
    page_title = "Судебные дела"
    context_object_name = "court_cases"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingCourtCase.objects.filter(subsystem=sub).select_related(
            "inspection", "prescription"
        )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(case_number__icontains=q)
                | Q(court_name__icontains=q)
                | Q(defendant_name__icontains=q)
            )
        return qs.order_by("-next_hearing_date", "-case_number")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["status_choices"] = HousingCourtCase.Status.choices
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "court_cases"
        ctx["bulk_status_choices"] = HousingCourtCase.Status.choices
        return ctx


class UzhvCourtCaseCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/court_case_form.html"
    page_title = "Новое судебное дело"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        ctx["form"] = HousingCourtCaseForm(subsystem=sub)
        ctx["court_case"] = None
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingCourtCaseForm(request.POST, subsystem=sub)
        if form.is_valid():
            case = form.save(commit=False)
            case.subsystem = sub
            case.save()
            messages.success(request, "Судебное дело зарегистрировано")
            return redirect("uzhv-court-cases")
        return self.render_to_response({**self.get_context_data(), "form": form})


class UzhvCourtCaseUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/court_case_form.html"
    page_title = "Судебное дело"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        court_case = get_object_or_404(HousingCourtCase, pk=self.kwargs["pk"], subsystem=sub)
        ctx["court_case"] = court_case
        ctx["page_title"] = court_case.case_number
        ctx["form"] = HousingCourtCaseForm(instance=court_case, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        court_case = get_object_or_404(HousingCourtCase, pk=pk, subsystem=sub)
        form = HousingCourtCaseForm(request.POST, instance=court_case, subsystem=sub)
        if form.is_valid():
            form.save()
            messages.success(request, "Судебное дело сохранено")
            return redirect("uzhv-court-cases")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "court_case": court_case}
        )


class UzhvEnforcementProceedingsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/enforcement_list.html"
    page_title = "Исполнительные производства"
    context_object_name = "proceedings"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingEnforcementProceeding.objects.filter(subsystem=sub).select_related(
            "court_case"
        )
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(proceeding_number__icontains=q)
                | Q(debtor_name__icontains=q)
                | Q(court_case__case_number__icontains=q)
            )
        status = self.request.GET.get("status")
        if status in dict(HousingEnforcementProceeding.Status.choices):
            qs = qs.filter(status=status)
        return qs.order_by("-initiated_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["status_choices"] = HousingEnforcementProceeding.Status.choices
        return ctx


class UzhvEnforcementProceedingCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/enforcement_form.html"
    page_title = "Новое исполнительное производство"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {"initiated_at": timezone.now().date()}
        court_id = self.request.GET.get("court_case")
        if court_id and court_id.isdigit():
            cc = HousingCourtCase.objects.filter(pk=int(court_id), subsystem=sub).first()
            if cc:
                initial.update(
                    {
                        "court_case": cc.pk,
                        "debtor_name": cc.defendant_name,
                        "check_address": cc.check_address,
                        "proceeding_number": cc.ufssp_reference or "",
                    }
                )
        ctx["form"] = kwargs.get(
            "form", HousingEnforcementProceedingForm(initial=initial, subsystem=sub)
        )
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingEnforcementProceedingForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.save()
            cc = obj.court_case
            if cc.ufssp_reference != obj.proceeding_number:
                cc.ufssp_reference = obj.proceeding_number
                if cc.status not in (
                    HousingCourtCase.Status.CLOSED,
                    HousingCourtCase.Status.CANCELLED,
                ):
                    cc.status = HousingCourtCase.Status.ENFORCEMENT
                cc.save(update_fields=["ufssp_reference", "status", "updated_at"])
            messages.success(request, "Исполнительное производство зарегистрировано")
            return redirect("uzhv-enforcement")
        return self.render_to_response(self.get_context_data(form=form))


class UzhvEnforcementProceedingUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/enforcement_form.html"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        proceeding = get_object_or_404(
            HousingEnforcementProceeding, pk=self.kwargs["pk"], subsystem=sub
        )
        ctx["proceeding"] = proceeding
        ctx["page_title"] = f"ИП {proceeding.proceeding_number}"
        ctx["form"] = HousingEnforcementProceedingForm(instance=proceeding, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        proceeding = get_object_or_404(HousingEnforcementProceeding, pk=pk, subsystem=sub)
        form = HousingEnforcementProceedingForm(request.POST, instance=proceeding, subsystem=sub)
        if form.is_valid():
            obj = form.save()
            if obj.status == HousingEnforcementProceeding.Status.COMPLETED and not obj.completed_at:
                obj.completed_at = timezone.now().date()
                obj.save(update_fields=["completed_at", "updated_at"])
            messages.success(request, "Сохранено")
            return redirect("uzhv-enforcement")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "proceeding": proceeding}
        )


class UzhvInteragencyListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/interagency_list.html"
    page_title = "Межведомственные запросы"
    context_object_name = "requests"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        sync_overdue_interagency(sub)
        from delayu.services.uzhv_overdue import (
            filter_interagency_assignee,
            parse_hub_assignee_filter,
        )

        assignee_id = parse_hub_assignee_filter(self.request.GET, self.request.user)
        qs = HousingInteragencyRequest.objects.filter(subsystem=sub).select_related(
            "citizen", "housing_case", "housing_case__assignee", "created_by"
        )
        status = self.request.GET.get("status")
        if status:
            qs = qs.filter(status=status)
        if self.request.GET.get("overdue") == "1":
            today = timezone.now().date()
            qs = qs.exclude(
                status__in=[
                    HousingInteragencyRequest.Status.ANSWERED,
                    HousingInteragencyRequest.Status.CANCELLED,
                ]
            ).filter(due_date__lt=today)
        qs = filter_interagency_assignee(qs, assignee_id)
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(request_number__icontains=q)
                | Q(recipient_name__icontains=q)
                | Q(subject__icontains=q)
            )
        return qs.order_by("-sent_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        from delayu.services.uzhv_bulk import subsystem_assignees

        ctx["status_choices"] = HousingInteragencyRequest.Status.choices
        ctx["can_create"] = _can(self.request.user, "create")
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["filter_overdue"] = self.request.GET.get("overdue", "")
        ctx["filter_assignee"] = self.request.GET.get("assignee", "")
        ctx["assignee_users"] = subsystem_assignees(self.get_subsystem())
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "interagency"
        ctx["bulk_status_choices"] = HousingInteragencyRequest.Status.choices
        return ctx


class UzhvInteragencyCreateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/interagency_form.html"
    page_title = "Новый межвед. запрос"
    required_action = "create"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        initial = {
            "request_number": next_interagency_number(sub),
            "channel": HousingInteragencyRequest.Channel.MANUAL,
            "due_date": timezone.now().date() + timedelta(days=30),
        }
        ctx["form"] = HousingInteragencyRequestForm(initial=initial, subsystem=sub)
        return ctx

    def post(self, request):
        sub = self.get_subsystem()
        form = HousingInteragencyRequestForm(request.POST, subsystem=sub)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.subsystem = sub
            obj.created_by = request.user
            if obj.status == HousingInteragencyRequest.Status.ANSWERED and not obj.answered_at:
                obj.answered_at = timezone.now().date()
            obj.save()
            messages.success(request, "Запрос зарегистрирован")
            return redirect("uzhv-interagency")
        return self.render_to_response({**self.get_context_data(), "form": form})


class UzhvInteragencyUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/interagency_form.html"
    page_title = "Межведомственный запрос"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        obj = get_object_or_404(HousingInteragencyRequest, pk=self.kwargs["pk"], subsystem=sub)
        ctx["interagency"] = obj
        ctx["page_title"] = obj.request_number
        ctx["form"] = HousingInteragencyRequestForm(instance=obj, subsystem=sub)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        obj = get_object_or_404(HousingInteragencyRequest, pk=pk, subsystem=sub)
        form = HousingInteragencyRequestForm(request.POST, instance=obj, subsystem=sub)
        if form.is_valid():
            saved = form.save()
            if saved.status == HousingInteragencyRequest.Status.ANSWERED and not saved.answered_at:
                saved.answered_at = timezone.now().date()
                saved.save(update_fields=["answered_at"])
            messages.success(request, "Запрос сохранён")
            return redirect("uzhv-interagency")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "interagency": obj}
        )


class UzhvAdminProtocolsListView(UzhvSubsystemMixin, ModulePermissionMixin, ListView):
    template_name = "platform/uzhv/admin_protocols_list.html"
    page_title = "Протоколы об АП"
    context_object_name = "protocols"
    paginate_by = 25

    def get_queryset(self):
        sub = self.get_subsystem()
        qs = HousingAdminProtocol.objects.filter(
            inspection__subsystem=sub
        ).select_related("inspection", "inspection__building")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(protocol_number__icontains=q)
                | Q(violator_name__icontains=q)
                | Q(legal_article__icontains=q)
            )
        status = self.request.GET.get("status")
        if status in dict(HousingAdminProtocol.Status.choices):
            qs = qs.filter(status=status)
        return qs.order_by("-protocol_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_change"] = _can(self.request.user, "change")
        ctx["bulk_enabled"] = True
        ctx["bulk_entity"] = "admin_protocols"
        ctx["bulk_status_choices"] = HousingAdminProtocol.Status.choices
        ctx["status_choices"] = HousingAdminProtocol.Status.choices
        ctx["filter_status"] = self.request.GET.get("status", "")
        return ctx


class UzhvAdminProtocolUpdateView(UzhvSubsystemMixin, ModulePermissionMixin, TemplateView):
    template_name = "platform/uzhv/admin_protocol_form.html"
    page_title = "Протокол об АП"
    required_action = "change"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = self.get_subsystem()
        protocol = get_object_or_404(
            HousingAdminProtocol.objects.select_related("inspection"),
            pk=self.kwargs["pk"],
            inspection__subsystem=sub,
        )
        ctx["protocol"] = protocol
        ctx["page_title"] = protocol.protocol_number
        ctx["form"] = HousingAdminProtocolForm(instance=protocol)
        return ctx

    def post(self, request, pk):
        sub = self.get_subsystem()
        protocol = get_object_or_404(
            HousingAdminProtocol, pk=pk, inspection__subsystem=sub
        )
        form = HousingAdminProtocolForm(request.POST, instance=protocol)
        if form.is_valid():
            form.save()
            messages.success(request, "Протокол сохранён")
            return redirect("uzhv-admin-protocols")
        return self.render_to_response(
            {**self.get_context_data(), "form": form, "protocol": protocol}
        )


class UzhvBulkActionView(UzhvSubsystemMixin, ModulePermissionMixin, View):
    """Массовый экспорт и смена статуса в реестрах УЖВ."""

    def post(self, request):
        from delayu.services.uzhv_bulk import (
            bulk_close_contracts,
            bulk_set_appeal_assignee,
            bulk_set_appeal_status,
            bulk_set_case_assignee,
            bulk_set_case_status,
            bulk_set_court_case_status,
            bulk_set_inspection_status,
            bulk_set_interagency_status,
            bulk_set_admin_protocol_status,
            bulk_set_orphan_housing_status,
            bulk_set_young_family_meets_criteria,
            bulk_set_young_family_program,
            bulk_set_prescription_status,
            export_admin_protocols_csv,
            export_appeals_csv,
            export_cases_csv,
            export_citizens_csv,
            export_contracts_csv,
            export_court_cases_csv,
            export_inspections_csv,
            export_interagency_csv,
            export_orphans_csv,
            export_prescriptions_csv,
            export_young_families_csv,
        )

        sub = self.get_subsystem()
        entity = request.POST.get("entity", "")
        action = request.POST.get("action", "")
        ids = [int(x) for x in request.POST.getlist("ids") if str(x).isdigit()]
        if not ids:
            messages.warning(request, "Не выбрано ни одной записи")
            return redirect(request.POST.get("next") or "uzhv-hub")

        if entity == "cases":
            if action == "export_csv":
                return export_cases_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_case_status(sub, ids, status, user=request.user)
                messages.success(request, f"Обновлено дел: {n}, очередь пересчитана")
            elif action == "assign":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                raw = request.POST.get("assignee", "").strip()
                user_id = int(raw) if raw.isdigit() else None
                n = bulk_set_case_assignee(sub, ids, user_id)
                messages.success(request, f"Назначено дел: {n}")
            return redirect(request.POST.get("next") or "uzhv-cases")

        if entity == "appeals":
            if action == "export_csv":
                return export_appeals_csv(sub, ids)
            if action == "status":
                if not user_can(request.user, "M24", "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_appeal_status(sub, ids, status, user=request.user)
                messages.success(request, f"Обновлено обращений: {n}")
            elif action == "assign":
                if not user_can(request.user, "M24", "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                raw = request.POST.get("assignee", "").strip()
                user_id = int(raw) if raw.isdigit() else None
                n = bulk_set_appeal_assignee(sub, ids, user_id)
                messages.success(request, f"Назначено обращений: {n}")
            return redirect(request.POST.get("next") or "uzhv-appeals")

        if entity == "inspections":
            if action == "export_csv":
                return export_inspections_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_inspection_status(sub, ids, status)
                messages.success(request, f"Обновлено проверок: {n}")
            return redirect(request.POST.get("next") or "uzhv-inspections")

        if entity == "interagency":
            if action == "export_csv":
                return export_interagency_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_interagency_status(sub, ids, status)
                messages.success(request, f"Обновлено запросов: {n}")
            return redirect(request.POST.get("next") or "uzhv-interagency")

        if entity == "contracts":
            if action == "export_csv":
                return export_contracts_csv(sub, ids)
            if action == "close":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                n = bulk_close_contracts(sub, ids)
                messages.success(request, f"Закрыто договоров: {n}")
            return redirect(request.POST.get("next") or "uzhv-contracts")

        if entity == "prescriptions":
            if action == "export_csv":
                return export_prescriptions_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_prescription_status(sub, ids, status)
                messages.success(request, f"Обновлено предписаний: {n}")
            return redirect(request.POST.get("next") or "uzhv-prescriptions")

        if entity == "court_cases":
            if action == "export_csv":
                return export_court_cases_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_court_case_status(sub, ids, status)
                messages.success(request, f"Обновлено судебных дел: {n}")
            return redirect(request.POST.get("next") or "uzhv-court-cases")

        if entity == "citizens":
            if action == "export_csv":
                return export_citizens_csv(sub, ids, user=request.user)
            return redirect(request.POST.get("next") or "uzhv-citizens")

        if entity == "young_families":
            if action == "export_csv":
                return export_young_families_csv(sub, ids)
            if action == "meets_criteria":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                meets = request.POST.get("meets") == "1"
                n = bulk_set_young_family_meets_criteria(sub, ids, meets=meets)
                label = "соответствуют" if meets else "не соответствуют"
                messages.success(request, f"Обновлено записей ({label}): {n}")
            if action == "program":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                program = request.POST.get("program", "")
                n = bulk_set_young_family_program(sub, ids, program)
                messages.success(request, f"Обновлено программ: {n}")
            return redirect(request.POST.get("next") or "uzhv-young-families")

        if entity == "orphans":
            if action == "export_csv":
                return export_orphans_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_orphan_housing_status(sub, ids, status)
                messages.success(request, f"Обновлено записей: {n}")
            return redirect(request.POST.get("next") or "uzhv-orphans")

        if entity == "admin_protocols":
            if action == "export_csv":
                return export_admin_protocols_csv(sub, ids)
            if action == "status":
                if not _can(request.user, "change"):
                    from django.core.exceptions import PermissionDenied

                    raise PermissionDenied
                status = request.POST.get("status", "")
                n = bulk_set_admin_protocol_status(sub, ids, status)
                messages.success(request, f"Обновлено протоколов: {n}")
            return redirect(request.POST.get("next") or "uzhv-admin-protocols")

        messages.error(request, "Неизвестная операция")
        return redirect(request.POST.get("next") or "uzhv-hub")
