"""Функциональные представления платформы (этапы 1–10)."""
import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from delayu.forms import (
    DocumentUploadForm,
    MembershipForm,
    SubsystemForm,
)
from delayu.menu import get_active_membership
from delayu.mixins import ModulePermissionMixin, PlatformLayoutMixin
from delayu.models import (
    ActivityEvent,
    AuditLog,
    BPMTemplate,
    CaseFile,
    Correspondence,
    Department,
    DocumentFile,
    Favorite,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    SavedFilter,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
    TaskItem,
    UserProfile,
)
from delayu.services import archive, audit, bpm
from delayu.services.access import get_membership_or_403, user_can

User = get_user_model()


def _ctx_membership(view):
    return get_membership_or_403(view.request)


from delayu.services.workplace import log_activity as _log_activity

# M01 — delayu.views_m01
# M07–M14 — delayu.views_workplace

# M22 — delayu.views_cases

class CaseArchiveView(ModulePermissionMixin, View):
    module_code = "M06"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(CaseFile, pk=pk, subsystem=m.subsystem)
        if case.is_archived:
            messages.warning(request, "Дело уже в архиве.")
            return redirect("platform-case-detail", pk=pk)
        reason = request.POST.get("archive_reason", "").strip()
        years_raw = request.POST.get("retention_years", "5").strip()
        try:
            retention_years = int(years_raw) if years_raw else 5
        except ValueError:
            retention_years = 5
        if retention_years < 0:
            retention_years = 0
        archive.archive_case(
            case,
            request.user,
            reason=reason,
            retention_years=retention_years if retention_years > 0 else None,
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "archive.case",
            "CaseFile",
            case.pk,
            {"retention_years": retention_years},
            request,
        )
        messages.success(request, "Дело переведено в архив.")
        return redirect("platform-case-detail", pk=pk)


# M37–M41 — delayu.views_comms

# M33–M36 — delayu.views_bpm

# M23 — delayu.views_registries
# M24–M32 — delayu.views_correspondence

# M05 — delayu.views_documents

# M15–M21 — delayu.views_analytics

# M46 — delayu.views_audio
# M47–M66 — delayu.views_ai

# --- M02-M04 админ (M03 — delayu.views_users) ---
# M02 — delayu.views_roles; M04 — delayu.views_structure

# M42–M45 — delayu.views_integrations

# M73–M77 — delayu.views_operations

# M78–M82 — delayu.views_exploitation
# M83–M86 — delayu.views_ux

# --- M06 архив дел (список и операции — delayu.views_archive) ---

# --- Home enhanced ---
class AcceptanceView(LoginRequiredMixin, PlatformLayoutMixin, TemplateView):
    template_name = "platform/acceptance.html"


class HomeView(LoginRequiredMixin, PlatformLayoutMixin, TemplateView):
    template_name = "platform/home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = get_active_membership(self.request.user)
        if not m:
            ctx["stats"] = {"cases": 0, "inbox": 0, "tasks": 0, "bpm_pending": 0, "documents": 0}
            ctx["kpi"] = {}
            ctx["module_breakdown"] = []
            ctx["queue_tabs"] = []
            ctx["weekly_summary"] = {"new_cases_week": 0, "overdue_cases": 0}
            ctx["dashboard_json"] = "{}"
            ctx["department_rows"] = []
            ctx["overdue_cases"] = []
            ctx["activity_feed"] = []
            ctx["recent_cases"] = []
            ctx["quality"] = {}
            ctx["retention_alerts"] = []
            ctx["retention_expired_count"] = 0
            return ctx
        from delayu.services.analytics import (
            department_analytics,
            home_dashboard_payload,
            home_module_breakdown,
            home_queue_tabs,
            home_weekly_summary,
            kpi_dashboard,
            quality_metrics,
        )
        from delayu.services.retention import retention_alerts, retention_expired

        sub = m.subsystem
        kpi = kpi_dashboard(sub)
        today = timezone.now().date()
        ctx["kpi"] = kpi
        ctx["module_breakdown"] = home_module_breakdown(sub)
        ctx["stats"] = {
            "cases": kpi.get("cases_total", 0),
            "inbox": kpi.get("corr_in_work", 0),
            "tasks": kpi.get("tasks_open", 0),
            "bpm_pending": kpi.get("bpm_pending", 0),
            "documents": DocumentFile.objects.filter(
                subsystem=sub, is_current=True
            ).count(),
        }
        ctx["queue_tabs"] = home_queue_tabs(sub)
        ctx["weekly_summary"] = home_weekly_summary(sub)
        ctx["dashboard_json"] = json.dumps(
            home_dashboard_payload(sub, days=30), ensure_ascii=False
        )
        ctx["department_rows"] = department_analytics(sub, m.organization)[:10]
        ctx["overdue_cases"] = (
            CaseFile.objects.filter(
                subsystem=sub,
                is_archived=False,
                due_date__lt=today,
            )
            .exclude(status=CaseFile.Status.DONE)
            .select_related("assignee")
            .order_by("due_date")[:8]
        )
        ctx["recent_cases"] = (
            CaseFile.objects.filter(subsystem=sub, is_archived=False)
            .select_related("assignee")
            .order_by("-updated_at")[:8]
        )
        ctx["activity_feed"] = (
            ActivityEvent.objects.filter(subsystem=sub)
            .select_related("actor")
            .order_by("-created_at")[:12]
        )
        ctx["quality"] = quality_metrics(sub)
        ctx["retention_alerts"] = retention_alerts(sub)
        ctx["retention_expired_count"] = retention_expired(sub)
        return ctx
