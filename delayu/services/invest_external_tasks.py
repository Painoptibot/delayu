"""Автозадачи МО/ТП и фиксация ответов (п.21–25)."""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestExternalTask, InvestIntegrationEvent, InvestProject
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_journal import finish_event, log_event


@transaction.atomic
def ensure_mo_task(project: InvestProject, *, due_days: int = 5) -> InvestExternalTask | None:
    if not flag_enabled(project.subsystem, "auto_mo_tasks"):
        return None
    existing = project.external_tasks.filter(
        kind=InvestExternalTask.Kind.MO,
        status__in=(
            InvestExternalTask.Status.OPEN,
            InvestExternalTask.Status.OVERDUE,
            InvestExternalTask.Status.ANSWERED,
            InvestExternalTask.Status.AGREED,
            InvestExternalTask.Status.REJECTED,
        ),
    ).first()
    if existing:
        return existing
    task = InvestExternalTask.objects.create(
        subsystem=project.subsystem,
        project=project,
        organization=project.organization,
        kind=InvestExternalTask.Kind.MO,
        title=f"Подтвердить территориальные данные по {project.code}",
        due_at=timezone.now() + timedelta(days=due_days),
    )
    log_event(
        subsystem=project.subsystem,
        direction=InvestIntegrationEvent.Direction.OUT,
        channel=InvestIntegrationEvent.Channel.MO,
        event_type="mo.task_created",
        project=project,
        payload={"task_id": task.pk, "due_at": task.due_at.isoformat()},
        status=InvestIntegrationEvent.Status.DONE,
    )
    return task


@transaction.atomic
def ensure_tp_task(project: InvestProject, *, due_days: int = 7) -> InvestExternalTask | None:
    if not flag_enabled(project.subsystem, "auto_tp_tasks"):
        return None
    existing = project.external_tasks.filter(
        kind=InvestExternalTask.Kind.TP,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).first()
    if existing:
        return existing
    task = InvestExternalTask.objects.create(
        subsystem=project.subsystem,
        project=project,
        organization=project.organization,
        kind=InvestExternalTask.Kind.TP,
        title=f"Запрос ТП (сети/мощности) по {project.code}",
        due_at=timezone.now() + timedelta(days=due_days),
        response_payload={"template": "power_and_networks_v1"},
    )
    log_event(
        subsystem=project.subsystem,
        direction=InvestIntegrationEvent.Direction.OUT,
        channel=InvestIntegrationEvent.Channel.TP,
        event_type="tp.task_created",
        project=project,
        payload={"task_id": task.pk},
        status=InvestIntegrationEvent.Status.DONE,
    )
    return task


@transaction.atomic
def record_external_answer(
    task: InvestExternalTask,
    *,
    status: str,
    payload: dict | None = None,
) -> InvestExternalTask:
    if status not in InvestExternalTask.Status.values:
        raise ValueError("invalid status")
    task.status = status
    task.response_payload = payload or {}
    task.answered_at = timezone.now()
    task.save(update_fields=["status", "response_payload", "answered_at"])
    channel = (
        InvestIntegrationEvent.Channel.MO
        if task.kind == InvestExternalTask.Kind.MO
        else InvestIntegrationEvent.Channel.TP
    )
    event = log_event(
        subsystem=task.subsystem,
        direction=InvestIntegrationEvent.Direction.IN,
        channel=channel,
        event_type=f"{task.kind}.answer",
        project=task.project,
        payload={"task_id": task.pk, "status": status, "payload": payload or {}},
    )
    finish_event(event, status=InvestIntegrationEvent.Status.DONE, response={"ok": True})
    # машинный статус в external_ids проекта (п.25)
    ext = dict(task.project.external_ids or {})
    key = "mo_decision" if task.kind == InvestExternalTask.Kind.MO else "tp_decision"
    ext[key] = status
    task.project.external_ids = ext
    task.project.save(update_fields=["external_ids", "updated_at"])
    return task
