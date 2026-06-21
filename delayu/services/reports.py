from django.db.models import Count
from django.utils import timezone

from delayu.models import BPMTask, CaseFile, Correspondence, DocumentFile, TaskItem


def run_report(subsystem, query_key: str) -> dict:
    today = timezone.now().date()
    if query_key == "cases_summary":
        qs = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
        return {
            "rows": list(
                qs.values("status").annotate(cnt=Count("id")).order_by("status")
            ),
            "total": qs.count(),
            "overdue": qs.filter(due_date__lt=today)
            .exclude(status__in=[CaseFile.Status.DONE, CaseFile.Status.ARCHIVED])
            .count(),
        }
    if query_key == "correspondence_in":
        return {
            "rows": list(
                Correspondence.objects.filter(
                    subsystem=subsystem, direction=Correspondence.Direction.IN
                )
                .values("status")
                .annotate(cnt=Count("id"))
            ),
        }
    if query_key == "tasks_by_user":
        return {
            "rows": list(
                TaskItem.objects.filter(subsystem=subsystem, completed_at__isnull=True)
                .values("assignee__username")
                .annotate(cnt=Count("id"))
            ),
        }
    if query_key == "docs_by_type":
        return {
            "rows": list(
                DocumentFile.objects.filter(subsystem=subsystem, is_current=True)
                .values("doc_type")
                .annotate(cnt=Count("id"))
            ),
        }
    if query_key == "bpm_pending":
        return {
            "rows": list(
                BPMTask.objects.filter(
                    instance__case__subsystem=subsystem, status=BPMTask.Status.PENDING
                )
                .values("step_name")
                .annotate(cnt=Count("id"))
            ),
        }
    return {"rows": [], "message": "Неизвестный отчёт"}
