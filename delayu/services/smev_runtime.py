"""Runtime СМЭВ 3.x — формирование конверта и отправка через очередь интеграций."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from delayu.models import IntegrationMessage


def resolve_smev_transport(config: dict) -> str:
    """Определить транспорт с учётом prod-флагов и настроек проекта."""
    if getattr(settings, "DELAYU_SMEV_FORCE_SIMULATED", False):
        return "simulated"
    return (config.get("transport") or "simulated").lower()


def is_production_transport(config: dict) -> bool:
    """HTTP без test_mode — боевой контур."""
    return resolve_smev_transport(config) == "http" and not config.get("test_mode", True)


def build_smev_envelope(payload: dict, config: dict) -> dict:
    """Собрать конверт СМЭВ 3.x из payload и настроек endpoint."""
    message_type = payload.get("message_type") or config.get("message_type") or "Request"
    body = payload.get("body")
    if body is None:
        body = {k: v for k, v in payload.items() if k not in ("message_type", "smev_envelope")}
    transport = resolve_smev_transport(config)
    return {
        "version": config.get("smev_version") or "3.x",
        "message_type": message_type,
        "client_id": config.get("client_id") or "",
        "test_mode": config.get("test_mode", True) if transport == "http" else True,
        "transport": transport,
        "body": body,
        "created_at": timezone.now().isoformat(),
    }


def smev_http_headers(config: dict, envelope: dict) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Delayu-SMEV/1.0",
        "X-SMEV-Message-Type": str(envelope.get("message_type") or "Request"),
        "X-SMEV-Client-Id": str(envelope.get("client_id") or ""),
    }
    if is_production_transport(config):
        headers["X-SMEV-Production"] = "1"
    else:
        headers["X-SMEV-Test"] = "1"
    custom = config.get("http_headers") or {}
    if isinstance(custom, dict):
        headers.update({str(k): str(v) for k, v in custom.items()})
    secret = (config.get("secret") or config.get("api_key") or "").strip()
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def process_smev_message(message: IntegrationMessage) -> IntegrationMessage:
    """Обработать исходящее сообщение СМЭВ (simulated или HTTP-транспорт)."""
    ep = message.endpoint
    config = ep.config or {}
    envelope = build_smev_envelope(message.payload or {}, config)
    transport = resolve_smev_transport(config)
    merged = dict(message.payload or {})
    merged["smev_envelope"] = envelope

    if transport == "http":
        url = (config.get("url") or config.get("webhook_url") or "").strip()
        if not url:
            message.status = IntegrationMessage.Status.FAILED
            message.error_text = "Для HTTP-транспорта укажите url в config endpoint"
            message.save(update_fields=["status", "error_text"])
            return message
        if message.retry_count >= ep.max_retries:
            message.status = IntegrationMessage.Status.DEAD_LETTER
            message.error_text = "Превышено число повторов"
            message.save(update_fields=["status", "error_text"])
            return message
        message.retry_count += 1
        body_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        timeout = int(config.get("http_timeout") or 25)
        try:
            req = urllib.request.Request(
                url,
                data=body_bytes,
                headers=smev_http_headers(config, envelope),
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")[:4000]
                ok = 200 <= resp.status < 300
            if ok:
                merged["smev_http_status"] = resp.status
                if raw:
                    try:
                        merged["smev_response"] = json.loads(raw)
                    except json.JSONDecodeError:
                        merged["smev_response_text"] = raw
                message.payload = merged
                message.status = IntegrationMessage.Status.SENT
                message.error_text = ""
                message.processed_at = timezone.now()
                message.external_id = message.external_id or f"SMEV-{message.pk}"
            else:
                message.status = IntegrationMessage.Status.PENDING
                message.error_text = f"HTTP {resp.status}"
            message.save()
            return message
        except urllib.error.URLError as exc:
            if message.retry_count >= ep.max_retries:
                message.status = IntegrationMessage.Status.DEAD_LETTER
            else:
                message.status = IntegrationMessage.Status.PENDING
            message.error_text = str(exc)[:2000]
            message.save()
            return message

    message.payload = merged
    message.status = IntegrationMessage.Status.SENT
    message.error_text = ""
    message.processed_at = timezone.now()
    message.external_id = message.external_id or f"SMEV-{message.pk}"
    message.save()
    return message
