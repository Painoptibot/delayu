"""M06 — архив дел: реестр, карточка, legal hold, восстановление, экспорт."""
from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from delayu.mixins import CriticalReauthMixin, ModulePermissionMixin
from delayu.models import CaseFile
from delayu.services import archive as archive_service
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.retention import purge_expired_cases, retention_expired
from delayu.views_platform import _ctx_membership


class ArchiveCasesListView(ModulePermissionMixin, ListView):
    module_code = "M06"
    model = CaseFile
    template_name = "platform/archive/cases_list.html"
    context_object_name = "cases"
    paginate_by = 25

    def get_queryset(self):
        m = _ctx_membership(self)
        qs = (
            CaseFile.objects.filter(subsystem=m.subsystem, is_archived=True)
            .select_related("organization", "assignee", "created_by", "archived_by")
            .annotate(document_count=Count("documents"))
            .order_by("-archived_at")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q))
        lh = self.request.GET.get("legal_hold")
        if lh == "1":
            qs = qs.filter(legal_hold=True)
        elif lh == "0":
            qs = qs.filter(legal_hold=False)
        exp = self.request.GET.get("expiring")
        if exp == "1":
            from django.utils import timezone

            until = timezone.now().date() + timedelta(days=90)
            qs = qs.filter(retention_until__isnull=False, retention_until__lte=until)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Архив дел"
        ctx["search_q"] = self.request.GET.get("q", "")
        ctx["filter_legal_hold"] = self.request.GET.get("legal_hold", "")
        ctx["filter_expiring"] = self.request.GET.get("expiring", "")
        ctx["can_change"] = user_can(self.request.user, "M06", "change")
        ctx["can_archive"] = user_can(self.request.user, "M06", "archive")
        ctx["can_delete"] = user_can(self.request.user, "M06", "delete")
        ctx["expired_count"] = retention_expired(m.subsystem)
        ctx["can_purge"] = ctx["can_delete"] and ctx["expired_count"] > 0
        return ctx


class ArchivePurgeExpiredView(CriticalReauthMixin, ModulePermissionMixin, View):
    module_code = "M06"
    required_action = "delete"

    def post(self, request):
        m = _ctx_membership(self)
        dry_run = request.POST.get("execute") != "1"
        result = purge_expired_cases(m.subsystem, dry_run=dry_run)
        if dry_run:
            messages.info(
                request,
                f"Пробный прогон: {result['count']} дел к удалению. "
                f"Примеры: {', '.join(result.get('sample') or []) or '—'}",
            )
        else:
            audit.log_action(
                request.user,
                m.subsystem,
                "archive.purge",
                "CaseFile",
                "",
                {"count": result["count"], "sample": result.get("sample", [])},
                request,
            )
            messages.success(request, f"Удалено записей: {result.get('deleted', result['count'])}")
        return redirect("platform-archive-cases")


class ArchiveCaseModalView(ModulePermissionMixin, View):
    module_code = "M06"

    def get(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(
            CaseFile, pk=pk, subsystem=m.subsystem, is_archived=True
        )
        ctx = {
            "case": case,
            "can_change": user_can(request.user, "M06", "change"),
            "can_archive": user_can(request.user, "M06", "archive"),
        }
        return render(request, "platform/archive/_case_modal.html", ctx)


class ArchiveCaseLegalHoldView(ModulePermissionMixin, View):
    module_code = "M06"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(
            CaseFile, pk=pk, subsystem=m.subsystem, is_archived=True
        )
        new_val = request.POST.get("legal_hold") == "1"
        archive_service.set_legal_hold(case, new_val)
        audit.log_action(
            request.user,
            m.subsystem,
            "archive.legal_hold",
            "CaseFile",
            case.pk,
            {"legal_hold": new_val},
            request,
        )
        messages.success(
            request,
            "Legal hold включён." if new_val else "Legal hold снят.",
        )
        return redirect(f"/archive/cases/?open={pk}")


class ArchiveCaseRestoreView(ModulePermissionMixin, View):
    module_code = "M06"
    required_action = "archive"

    def post(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(
            CaseFile, pk=pk, subsystem=m.subsystem, is_archived=True
        )
        try:
            archive_service.restore_case(case, request.user)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(f"/archive/cases/?open={pk}")
        audit.log_action(
            request.user, m.subsystem, "archive.restore", "CaseFile", case.pk, request=request
        )
        messages.success(request, "Дело восстановлено из архива.")
        return redirect("platform-case-detail", pk=pk)


class ArchiveCaseExportView(ModulePermissionMixin, View):
    module_code = "M06"

    def get(self, request, pk):
        m = _ctx_membership(self)
        case = get_object_or_404(
            CaseFile, pk=pk, subsystem=m.subsystem, is_archived=True
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "archive.export_stub",
            "CaseFile",
            case.pk,
            request=request,
        )
        body = (
            f"Экспорт комплекта архивного дела {case.number}\n"
            f"{case.title}\n\n"
            "Формирование ZIP/PDF и передача во внешние системы — этап 2 ТЗ (M06).\n"
        )
        return HttpResponse(body, content_type="text/plain; charset=utf-8")
