"""Эскалации SLA roadmap и задач МО/ТП (п.14, 24)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from delayu.models_invest import InvestExternalTask, InvestIntegrationEvent, InvestRoadmapItem
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_journal import log_event
from delayu.services.invest_roadmap import mark_overdue


ESCALATION_LADDER_HOURS = (24, 72, 120)  # D+1 / D+3 / D+5


def escalate_overdue_roadmap(*, subsystem) -> int:
    if not flag_enabled(subsystem, "auto_escalations"):
        return 0
    mark_overdue()
    count = 0
    qs = InvestRoadmapItem.objects.filter(
        project__subsystem=subsystem,
        status=InvestRoadmapItem.Status.OVERDUE,
    ).select_related("project")
    for item in qs:
        ext = dict(item.project.external_ids or {})
        key = f"roadmap_escalated_{item.code}"
        if ext.get(key):
            continue
        ext[key] = timezone.now().isoformat()
        item.project.external_ids = ext
        item.project.save(update_fields=["external_ids", "updated_at"])
        log_event(
            subsystem=subsystem,
            direction=InvestIntegrationEvent.Direction.OUT,
            channel=InvestIntegrationEvent.Channel.BITRIX,
            event_type="sla.roadmap_overdue",
            project=item.project,
            payload={"roadmap_code": item.code, "title": item.title, "due_at": item.due_at.isoformat() if item.due_at else None},
            status=InvestIntegrationEvent.Status.DONE,
        )
        count += 1
    return count


def escalate_external_tasks(*, subsystem) -> int:
    if not flag_enabled(subsystem, "auto_escalations"):
        return 0
    now = timezone.now()
    count = 0
    qs = InvestExternalTask.objects.filter(
        subsystem=subsystem,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    )
    for task in qs:
        if task.due_at and task.due_at < now and task.status == InvestExternalTask.Status.OPEN:
            task.status = InvestExternalTask.Status.OVERDUE
            task.save(update_fields=["status"])
        if not task.due_at:
            continue
        overdue_hours = (now - task.due_at).total_seconds() / 3600
        target_level = 0
        for idx, hours in enumerate(ESCALATION_LADDER_HOURS, start=1):
            if overdue_hours >= hours:
                target_level = idx
        if target_level <= task.escalated_level:
            continue
        task.escalated_level = target_level
        task.last_reminded_at = now
        task.save(update_fields=["escalated_level", "last_reminded_at"])
        channel = (
            InvestIntegrationEvent.Channel.MO
            if task.kind == InvestExternalTask.Kind.MO
            else InvestIntegrationEvent.Channel.TP
        )
        log_event(
            subsystem=subsystem,
            direction=InvestIntegrationEvent.Direction.OUT,
            channel=channel,
            event_type="escalation.reminder",
            project=task.project,
            payload={
                "task_id": task.pk,
                "level": target_level,
                "kind": task.kind,
                "notify_dept": target_level >= 3,
            },
            status=InvestIntegrationEvent.Status.DONE,
        )
        count += 1
    return count
