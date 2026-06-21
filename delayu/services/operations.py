"""M74–M77 — формы, массовые операции, выгрузки, поручения."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from delayu.models import BulkOperation, CaseFile, ExportJob, FormSchema, ManagementDirective

User = get_user_model()


def ops_hub_metrics(subsystem):
    today = timezone.now().date()
    directives = ManagementDirective.objects.filter(subsystem=subsystem)
    return {
        "form_schemas": FormSchema.objects.filter(subsystem=subsystem, is_active=True).count(),
        "bulk_today": BulkOperation.objects.filter(
            subsystem=subsystem, created_at__date=today
        ).count(),
        "exports_pending": ExportJob.objects.filter(
            subsystem=subsystem, status=ExportJob.Status.PENDING
        ).count(),
        "directives_open": directives.exclude(status=ManagementDirective.Status.DONE).count(),
        "directives_overdue": directives.filter(
            status=ManagementDirective.Status.OVERDUE
        ).count(),
    }


def filter_form_schemas(subsystem, params=None):
    params = params or {}
    qs = FormSchema.objects.filter(subsystem=subsystem)
    target = (params.get("target") or "").strip()
    if target:
        qs = qs.filter(target=target)
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    return qs.order_by("target", "code")


def filter_bulk_operations(subsystem, params=None):
    params = params or {}
    qs = BulkOperation.objects.filter(subsystem=subsystem).select_related("user")
    op = (params.get("operation") or "").strip()
    if op:
        qs = qs.filter(operation=op)
    return qs.order_by("-created_at")


def run_bulk_operation(
    *,
    subsystem,
    user,
    operation: str,
    filter_params: dict,
    payload: dict,
) -> BulkOperation:
    """Демо-массовая операция по делам (M22)."""
    run = BulkOperation.objects.create(
        subsystem=subsystem,
        user=user,
        operation=operation,
        target_module="M22",
        filter_params=filter_params,
        payload=payload,
        status=BulkOperation.Status.PENDING,
    )
    qs = CaseFile.objects.filter(subsystem=subsystem, is_archived=False)
    status = (filter_params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    ids = filter_params.get("ids") or []
    if ids:
        qs = qs.filter(pk__in=ids)

    count = 0
    try:
        if operation == BulkOperation.Operation.STATUS:
            new_status = payload.get("new_status")
            if new_status:
                count = qs.update(status=new_status)
        elif operation == BulkOperation.Operation.ASSIGN:
            assignee_id = payload.get("assignee_id")
            if assignee_id:
                count = qs.update(assignee_id=assignee_id)
        elif operation == BulkOperation.Operation.EXPORT:
            count = qs.count()
        run.status = BulkOperation.Status.SUCCESS
        run.affected_count = count
        run.log = f"Обработано записей: {count}."
    except Exception as exc:
        run.status = BulkOperation.Status.FAILED
        run.log = str(exc)
    run.save()
    return run


def filter_export_jobs(subsystem, params=None):
    params = params or {}
    qs = ExportJob.objects.filter(subsystem=subsystem).select_related("user")
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-created_at")


def create_export_job(*, subsystem, user, kind: str, title: str, params: dict) -> ExportJob:
    job = ExportJob.objects.create(
        subsystem=subsystem,
        user=user,
        kind=kind,
        title=title,
        params=params,
        status=ExportJob.Status.PENDING,
    )
    if kind == "cases_csv":
        count = CaseFile.objects.filter(subsystem=subsystem, is_archived=False).count()
    else:
        count = 0
    job.records_count = count
    job.status = ExportJob.Status.SUCCESS
    job.finished_at = timezone.now()
    job.save()
    return job


def filter_directives(subsystem, params=None):
    params = params or {}
    qs = ManagementDirective.objects.filter(subsystem=subsystem).select_related(
        "assignee", "author", "case"
    )
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    assignee = params.get("assignee")
    if assignee:
        qs = qs.filter(assignee_id=assignee)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q))
    return qs.order_by("-created_at")


def mark_overdue_directives(subsystem):
    today = timezone.now().date()
    return ManagementDirective.objects.filter(
        subsystem=subsystem,
        due_date__lt=today,
        status__in=[
            ManagementDirective.Status.ISSUED,
            ManagementDirective.Status.IN_PROGRESS,
        ],
    ).update(status=ManagementDirective.Status.OVERDUE)
