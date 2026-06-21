from django.db.models import Q
from django.utils import timezone

from delayu.models import BPMInstance, BPMTask, BPMTemplate, CaseFile


def filter_templates(subsystem, params=None):
    params = params or {}
    qs = BPMTemplate.objects.filter(subsystem=subsystem)
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs.order_by("code")


def filter_instances(subsystem, params=None):
    params = params or {}
    qs = BPMInstance.objects.filter(template__subsystem=subsystem).select_related(
        "case", "template"
    )
    status = params.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(case__number__icontains=q) | Q(case__title__icontains=q))
    return qs.order_by("-started_at")


def filter_pending_tasks(subsystem, *, user=None, params=None):
    params = params or {}
    qs = BPMTask.objects.filter(
        instance__template__subsystem=subsystem,
        status=BPMTask.Status.PENDING,
    ).select_related("instance", "instance__case", "instance__template", "assignee")
    if user:
        qs = qs.filter(assignee=user)
    return qs.order_by("instance__started_at")


def start_process(template: BPMTemplate, case: CaseFile, initiator):
    steps = template.steps or []
    if not steps:
        return None
    first = steps[0]
    instance = BPMInstance.objects.create(
        template=template,
        case=case,
        current_step_id=first.get("id", "step1"),
    )
    assignee_id = first.get("assignee_id")
    if assignee_id:
        from django.contrib.auth import get_user_model

        assignee = get_user_model().objects.filter(pk=assignee_id).first() or initiator
    else:
        assignee = case.assignee or initiator
    task = BPMTask.objects.create(
        instance=instance,
        step_id=first.get("id", "step1"),
        step_name=first.get("name", "Согласование"),
        assignee=assignee,
    )
    from delayu.services.notify_dispatch import notify_bpm_task_assigned

    notify_bpm_task_assigned(task)
    return instance


def advance_process(task: BPMTask, approved: bool, comment: str = ""):
    task.status = BPMTask.Status.DONE if approved else BPMTask.Status.REJECTED
    task.comment = comment
    task.decided_at = timezone.now()
    task.save()
    instance = task.instance
    subsystem = instance.template.subsystem
    if not approved:
        instance.status = BPMInstance.Status.REJECTED
        instance.save()
        from delayu.services.notify_dispatch import notify_bpm_finished

        notify_bpm_finished(instance, approved=False)
        return instance
    steps = instance.template.steps or []
    ids = [s.get("id") for s in steps]
    try:
        idx = ids.index(task.step_id)
    except ValueError:
        idx = -1
    if idx + 1 >= len(steps):
        instance.status = BPMInstance.Status.COMPLETED
        instance.current_step_id = ""
        instance.save()
        from delayu.services.notify_dispatch import notify_bpm_finished

        notify_bpm_finished(instance, approved=True)
        return instance
    nxt = steps[idx + 1]
    instance.current_step_id = nxt.get("id", "")
    instance.save()
    from django.contrib.auth import get_user_model

    User = get_user_model()
    assignee = User.objects.filter(pk=nxt.get("assignee_id")).first() or task.assignee
    new_task = BPMTask.objects.create(
        instance=instance,
        step_id=nxt.get("id", ""),
        step_name=nxt.get("name", "Шаг"),
        assignee=assignee,
    )
    from delayu.services.notify_dispatch import notify_bpm_task_assigned

    notify_bpm_task_assigned(new_task)
    return instance
