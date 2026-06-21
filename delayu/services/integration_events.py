"""Исходящие события интеграций: webhook/rest + уведомления по шаблонам M78."""
from __future__ import annotations

from django.utils import timezone

from delayu.models import IntegrationEndpoint
from delayu.services.integrations import enqueue_outbound


def endpoint_handles_event(endpoint: IntegrationEndpoint, event_code: str) -> bool:
    events = endpoint.config.get("events")
    if events is None or events == []:
        return True
    if isinstance(events, str):
        events = [events]
    return "*" in events or event_code in events


def emit_integration_event(subsystem, event_code: str, data: dict) -> int:
    """
    Поставить в очередь исходящие сообщения на активные коннекторы webhook/rest,
    у которых в config.events указан event_code (или список пуст — все события).
  Возвращает число поставленных сообщений.
    """
    endpoints = IntegrationEndpoint.objects.filter(
        subsystem=subsystem,
        is_active=True,
        endpoint_type__in=(
            IntegrationEndpoint.EndpointType.WEBHOOK,
            IntegrationEndpoint.EndpointType.REST,
        ),
    )
    body = {
        "event": event_code,
        "subsystem_code": subsystem.code,
        "occurred_at": timezone.now().isoformat(),
        "data": data,
    }
    count = 0
    for ep in endpoints:
        if not endpoint_handles_event(ep, event_code):
            continue
        external_id = data.get("external_id") or f"{event_code}:{data.get('id', '')}"
        enqueue_outbound(ep, body, external_id=str(external_id)[:128])
        count += 1
    return count
