"""M07–M14 — рабочее место: активность, уведомления, сводки."""
from django.db.models import Count, Q
from django.utils import timezone

from delayu.models import (
    ActivityEvent,
    BPMTask,
    CaseFile,
    Notification,
    TaskItem,
)


def log_activity(subsystem, user, verb, target_repr, *, module_code="", link_path=""):
    return ActivityEvent.objects.create(
        subsystem=subsystem,
        actor=user,
        verb=verb,
        target_repr=str(target_repr)[:255],
        module_code=module_code[:8],
        link_path=link_path[:500],
    )


def cabinet_stats(user, subsystem):
    today = timezone.now().date()
    tasks_qs = TaskItem.objects.filter(subsystem=subsystem, assignee=user)
    return {
        "tasks_open": tasks_qs.filter(completed_at__isnull=True).count(),
        "tasks_overdue": tasks_qs.filter(
            completed_at__isnull=True, due_date__lt=today
        ).count(),
        "tasks_today": tasks_qs.filter(
            completed_at__isnull=True,
        ).filter(Q(due_date=today) | Q(due_date__isnull=True)).count(),
        "bpm_pending": BPMTask.objects.filter(
            assignee=user, status=BPMTask.Status.PENDING
        ).count(),
        "notifications_unread": Notification.objects.filter(
            user=user, subsystem=subsystem, is_read=False
        ).count(),
        "cases_assigned": CaseFile.objects.filter(
            subsystem=subsystem, assignee=user, is_archived=False
        ).count(),
    }


def today_inbox_preview(user, subsystem, *, limit=5):
    from delayu.models_business import Correspondence

    return list(
        Correspondence.objects.filter(
            subsystem=subsystem,
            direction=Correspondence.Direction.IN,
            assignee=user,
        )
        .order_by("-reg_date")[:limit]
    )


def gantt_rows(subsystem, user=None):
    """Строки для диаграммы Ганта: задачи с start_date или due_date."""
    qs = TaskItem.objects.filter(subsystem=subsystem).exclude(
        completed_at__isnull=False
    )
    if user:
        qs = qs.filter(assignee=user)
    rows = []
    for t in qs.select_related("case", "assignee"):
        start = t.start_date or t.due_date
        if not start:
            continue
        end = t.gantt_end_date
        rows.append(
            {
                "task": t,
                "start": start,
                "end": end,
                "days": max(1, t.duration_days),
            }
        )
    return sorted(rows, key=lambda r: r["start"])
