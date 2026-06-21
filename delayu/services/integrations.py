"""M42–M45 — шлюз интеграций, REST, СМЭВ, внешние ИС."""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import urllib.error
import urllib.request

from django.db.models import Q
from django.utils import timezone

from delayu.models import ApiClientKey, IntegrationEndpoint, IntegrationMessage


def filter_endpoints(subsystem, *, endpoint_type=None, params=None):
    params = params or {}
    qs = IntegrationEndpoint.objects.filter(subsystem=subsystem)
    if endpoint_type:
        if isinstance(endpoint_type, (list, tuple)):
            qs = qs.filter(endpoint_type__in=endpoint_type)
        else:
            qs = qs.filter(endpoint_type=endpoint_type)
    if params.get("active") == "1":
        qs = qs.filter(is_active=True)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))
    return qs.order_by("code")


def filter_messages(subsystem, params=None):
    params = params or {}
    qs = IntegrationMessage.objects.filter(endpoint__subsystem=subsystem).select_related(
        "endpoint"
    )
    status = params.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    ep = params.get("endpoint")
    if ep:
        qs = qs.filter(endpoint_id=ep)
    direction = params.get("direction", "").strip()
    if direction:
        qs = qs.filter(direction=direction)
    return qs.order_by("-created_at")


def hub_metrics(subsystem):
    msgs = IntegrationMessage.objects.filter(endpoint__subsystem=subsystem)
    return {
        "endpoints_active": IntegrationEndpoint.objects.filter(
            subsystem=subsystem, is_active=True
        ).count(),
        "pending": msgs.filter(status=IntegrationMessage.Status.PENDING).count(),
        "failed": msgs.filter(status=IntegrationMessage.Status.FAILED).count(),
        "sent_today": msgs.filter(
            status=IntegrationMessage.Status.SENT,
            created_at__date=timezone.now().date(),
        ).count(),
        "api_keys": ApiClientKey.objects.filter(subsystem=subsystem, is_active=True).count(),
    }


def enqueue_outbound(endpoint: IntegrationEndpoint, payload: dict, *, external_id=""):
    return IntegrationMessage.objects.create(
        endpoint=endpoint,
        direction=IntegrationMessage.Direction.OUT,
        payload=payload,
        status=IntegrationMessage.Status.PENDING,
        external_id=external_id,
    )


def _webhook_signature(secret: str, body: bytes) -> str:
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _process_http_outbound(message: IntegrationMessage) -> IntegrationMessage:
    """POST JSON на webhook_url / url из config коннектора."""
    ep = message.endpoint
    if message.retry_count >= ep.max_retries:
        message.status = IntegrationMessage.Status.DEAD_LETTER
        message.error_text = "Превышено число повторов"
        message.save(update_fields=["status", "error_text"])
        return message

    url = (ep.config.get("webhook_url") or ep.config.get("url") or "").strip()
    if not url:
        message.status = IntegrationMessage.Status.FAILED
        message.error_text = "В config не указан webhook_url или url"
        message.save(update_fields=["status", "error_text"])
        return message

    message.retry_count += 1
    body_bytes = json.dumps(message.payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": "Delayu-Integrations/1.0"}
    secret = (ep.config.get("secret") or ep.config.get("webhook_secret") or "").strip()
    sig = _webhook_signature(secret, body_bytes)
    if sig:
        headers["X-Delayu-Signature"] = f"sha256={sig}"

    try:
        req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            ok = 200 <= resp.status < 300
        if ok:
            message.status = IntegrationMessage.Status.SENT
            message.error_text = ""
            message.processed_at = timezone.now()
            message.external_id = message.external_id or f"MSG-{message.pk}"
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


def process_outbound(message: IntegrationMessage):
    """HTTP для webhook/rest; для остальных — демо-транспорт."""
    ep = message.endpoint
    if ep.endpoint_type in (
        IntegrationEndpoint.EndpointType.WEBHOOK,
        IntegrationEndpoint.EndpointType.REST,
    ):
        return _process_http_outbound(message)

    if message.retry_count >= ep.max_retries:
        message.status = IntegrationMessage.Status.DEAD_LETTER
        message.error_text = "Превышено число повторов"
        message.save()
        return message
    simulate_fail = ep.config.get("simulate_fail") is True
    message.retry_count += 1
    if simulate_fail and message.retry_count < ep.max_retries:
        message.status = IntegrationMessage.Status.PENDING
        message.error_text = "Демо: временная ошибка транспорта"
        message.save()
        return message
    message.status = IntegrationMessage.Status.SENT
    message.error_text = ""
    message.processed_at = timezone.now()
    message.external_id = message.external_id or f"MSG-{message.pk}"
    message.save()
    return message


def retry_message(message: IntegrationMessage):
    if message.status == IntegrationMessage.Status.DEAD_LETTER:
        message.status = IntegrationMessage.Status.PENDING
        message.retry_count = 0
        message.error_text = ""
        message.save(update_fields=["status", "retry_count", "error_text"])
        return process_outbound(message)
    if message.status not in (
        IntegrationMessage.Status.FAILED,
        IntegrationMessage.Status.PENDING,
    ):
        return message
    message.status = IntegrationMessage.Status.PENDING
    message.save(update_fields=["status"])
    return process_outbound(message)


def move_to_dead_letter(message: IntegrationMessage, *, reason: str = ""):
    message.status = IntegrationMessage.Status.DEAD_LETTER
    message.error_text = reason or message.error_text or "Перенесено в dead letter"
    message.save(update_fields=["status", "error_text"])
    return message


def process_pending_queue(subsystem, *, limit: int = 20) -> dict:
    pending = IntegrationMessage.objects.filter(
        endpoint__subsystem=subsystem,
        direction=IntegrationMessage.Direction.OUT,
        status=IntegrationMessage.Status.PENDING,
    ).select_related("endpoint")[:limit]
    ok = fail = 0
    for msg in pending:
        before = msg.status
        process_outbound(msg)
        msg.refresh_from_db()
        if msg.status == IntegrationMessage.Status.SENT:
            ok += 1
        elif msg.status in (
            IntegrationMessage.Status.FAILED,
            IntegrationMessage.Status.DEAD_LETTER,
        ):
            fail += 1
        elif before != msg.status:
            ok += 1
    return {"processed": ok + fail, "success": ok, "failed": fail}


def queue_metrics(subsystem):
    msgs = IntegrationMessage.objects.filter(endpoint__subsystem=subsystem)
    base = hub_metrics(subsystem)
    base["dead_letter"] = msgs.filter(status=IntegrationMessage.Status.DEAD_LETTER).count()
    base["queue_depth"] = msgs.filter(status=IntegrationMessage.Status.PENDING).count()
    return base


def receive_inbound(endpoint: IntegrationEndpoint, payload: dict):
    return IntegrationMessage.objects.create(
        endpoint=endpoint,
        direction=IntegrationMessage.Direction.IN,
        payload=payload,
        status=IntegrationMessage.Status.RECEIVED,
        processed_at=timezone.now(),
    )


def generate_api_key():
    raw = "dlyu_" + secrets.token_urlsafe(24)
    prefix = raw[:12]
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, prefix, key_hash


def create_api_key(*, subsystem, name, rate_limit=1000):
    raw, prefix, key_hash = generate_api_key()
    obj = ApiClientKey.objects.create(
        subsystem=subsystem,
        name=name,
        key_prefix=prefix,
        key_hash=key_hash,
        rate_limit_per_hour=rate_limit,
    )
    return obj, raw


def openapi_spec():
    from delayu.services.openapi_contract import build_openapi_spec

    return build_openapi_spec()
