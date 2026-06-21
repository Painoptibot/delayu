"""M22 — реестр дел: фильтры, карточка, нумерация."""
from django.db.models import Q
from django.utils import timezone

from delayu.models import BPMTask, CaseFile, Comment, DocumentFile, TaskItem


def filter_cases(subsystem, user, *, params, can_change_all: bool):
    from delayu.services.org_scope import apply_organization_scope

    qs = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
    qs = apply_organization_scope(user, subsystem, qs)
    if not can_change_all:
        from delayu.services.delegation import delegation_principals

        principals = delegation_principals(user, subsystem)
        assignee_filter = Q(assignee=user) | Q(created_by=user)
        if principals:
            assignee_filter |= Q(assignee_id__in=principals) | Q(created_by_id__in=principals)
        qs = qs.filter(assignee_filter)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q) | Q(description__icontains=q))
    status = params.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    assignee = params.get("assignee", "").strip()
    if assignee:
        qs = qs.filter(assignee_id=assignee)
    priority = params.get("priority", "").strip()
    if priority.isdigit():
        qs = qs.filter(priority=int(priority))
    if params.get("overdue") == "1":
        today = timezone.now().date()
        qs = qs.exclude(status=CaseFile.Status.DONE).filter(due_date__lt=today)
    return qs.select_related("assignee", "organization", "created_by").order_by("-updated_at")


def next_case_number(subsystem) -> str:
    last = CaseFile.objects.filter(subsystem=subsystem).order_by("-id").first()
    n = 1
    if last and "-" in last.number:
        try:
            n = int(last.number.split("-")[-1]) + 1
        except ValueError:
            n = CaseFile.objects.filter(subsystem=subsystem).count() + 1
    return f"{subsystem.code.upper()}-{timezone.now().year}-{n:04d}"


def case_card_context(case: CaseFile) -> dict:
    corr_count = case.correspondence.filter(is_deleted=False).count()
    return {
        "case": case,
        "doc_count": DocumentFile.objects.filter(case=case, is_current=True).count(),
        "task_count": TaskItem.objects.filter(case=case, completed_at__isnull=True).count(),
        "comment_count": Comment.objects.filter(case=case).count(),
        "corr_count": corr_count,
        "bpm_pending": BPMTask.objects.filter(
            instance__case=case, status=BPMTask.Status.PENDING
        ).count(),
    }
