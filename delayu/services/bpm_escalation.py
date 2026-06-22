"""Runtime-эскалации BPM по настройкам узлов Студии (#17)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from delayu.models import BPMTask, Role, SubsystemMembership


def step_config_for_task(task: BPMTask) -> dict:
    steps = task.instance.template.steps or []
    for step in steps:
        if step.get("id") == task.step_id:
            return step
    return {}


def resolve_role_assignee(subsystem, role_code: str, *, exclude_user=None):
    role = Role.objects.filter(subsystem=subsystem, code=role_code).first()
    if not role:
        return None
    qs = SubsystemMembership.objects.filter(subsystem=subsystem, role=role).select_related(
        "user"
    )
    if exclude_user:
        qs = qs.exclude(user=exclude_user)
    membership = qs.order_by("pk").first()
    return membership.user if membership else None


def process_bpm_escalations(subsystem, *, limit: int = 100) -> dict:
    """Переназначить просроченные задачи BPM на роль эскалации."""
    now = timezone.now()
    pending = (
        BPMTask.objects.filter(
            instance__template__subsystem=subsystem,
            status=BPMTask.Status.PENDING,
            is_escalated=False,
        )
        .select_related("instance", "instance__template", "assignee", "instance__case")
        .order_by("assigned_at", "pk")[:limit]
    )
    escalated = 0
    skipped = 0
    checked = 0
    for task in pending:
        checked += 1
        step = step_config_for_task(task)
        hours = int(step.get("escalate_after_hours") or 0)
        role_code = (step.get("escalate_to_role") or "").strip()
        if not hours or not role_code:
            skipped += 1
            continue
        assigned_at = task.assigned_at or task.instance.started_at or now
        if assigned_at + timedelta(hours=hours) > now:
            skipped += 1
            continue
        new_assignee = resolve_role_assignee(
            subsystem, role_code, exclude_user=task.assignee
        )
        if not new_assignee:
            skipped += 1
            continue
        old_assignee = task.assignee
        task.assignee = new_assignee
        task.is_escalated = True
        task.escalated_at = now
        if not task.assigned_at:
            task.assigned_at = assigned_at
        task.save(
            update_fields=["assignee", "is_escalated", "escalated_at", "assigned_at"]
        )
        from delayu.services import audit
        from delayu.services.notify_dispatch import notify_bpm_task_escalated

        audit.log_action(
            old_assignee,
            subsystem,
            "bpm.escalate",
            "BPMTask",
            task.pk,
            payload={
                "step_id": task.step_id,
                "from_user": old_assignee.username,
                "to_user": new_assignee.username,
                "role": role_code,
            },
        )
        notify_bpm_task_escalated(task, from_user=old_assignee, role_code=role_code)
        escalated += 1
    return {"escalated": escalated, "checked": checked, "skipped": skipped}
