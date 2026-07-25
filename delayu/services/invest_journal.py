"""Журнал интеграций, retry и dead-letter (п.19, 26)."""
from __future__ import annotations

import uuid

from django.utils import timezone

from delayu.models_invest import InvestIntegrationEvent


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def log_event(
    *,
    subsystem,
    direction: str,
    channel: str,
    event_type: str = "",
    external_id: str = "",
    payload: dict | None = None,
    project=None,
    site=None,
    correlation_id: str | None = None,
    status: str = InvestIntegrationEvent.Status.QUEUED,
) -> InvestIntegrationEvent:
    return InvestIntegrationEvent.objects.create(
        subsystem=subsystem,
        project=project,
        site=site,
        direction=direction,
        channel=channel,
        event_type=event_type,
        external_id=external_id or "",
        payload=payload or {},
        correlation_id=correlation_id or new_correlation_id(),
        status=status,
    )


def finish_event(event: InvestIntegrationEvent, *, status: str, response=None, error: str = ""):
    event.status = status
    event.response_payload = response or {}
    event.error_message = (error or "")[:512]
    event.finished_at = timezone.now()
    event.save(
        update_fields=["status", "response_payload", "error_message", "finished_at"]
    )
    return event


def retry_or_dead(event: InvestIntegrationEvent, *, error: str) -> InvestIntegrationEvent:
    event.retries += 1
    event.error_message = (error or "")[:512]
    if event.retries >= event.max_retries:
        event.status = InvestIntegrationEvent.Status.DEAD
        event.finished_at = timezone.now()
    else:
        event.status = InvestIntegrationEvent.Status.QUEUED
    event.save(update_fields=["retries", "error_message", "status", "finished_at"])
    return event


def requeue_dead_letters(*, subsystem, limit: int = 50) -> int:
    qs = InvestIntegrationEvent.objects.filter(
        subsystem=subsystem,
        status=InvestIntegrationEvent.Status.DEAD,
    ).order_by("id")[:limit]
    count = 0
    for event in qs:
        event.status = InvestIntegrationEvent.Status.QUEUED
        event.retries = 0
        event.error_message = ""
        event.finished_at = None
        event.save(update_fields=["status", "retries", "error_message", "finished_at"])
        count += 1
    return count
