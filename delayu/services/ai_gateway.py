"""Единая точка входа для ИИ-запросов: лимиты, ПДн, журнал (AI Gateway)."""
from __future__ import annotations

import re
import time
from typing import Callable

from delayu.models import AiRequestLog

EMAIL_RE = re.compile(r"[\w.-]+@[\w.-]+\.\w+")
PHONE_RE = re.compile(r"\+?\d[\d\s()-]{9,}")
SNILS_RE = re.compile(r"\d{3}-\d{3}-\d{3}\s?\d{2}")
PASSPORT_RE = re.compile(r"\d{4}\s?\d{6}")


class AiGatewayError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def contains_pii(text: str) -> bool:
    if not text:
        return False
    return bool(
        EMAIL_RE.search(text)
        or PHONE_RE.search(text)
        or SNILS_RE.search(text)
        or PASSPORT_RE.search(text)
    )


def redact_pii(text: str) -> str:
    out = EMAIL_RE.sub("[email]", text)
    out = PHONE_RE.sub("[phone]", out)
    out = SNILS_RE.sub("[snils]", out)
    out = PASSPORT_RE.sub("[passport]", out)
    return out


def _usage_today(subsystem) -> int:
    from django.utils import timezone

    today = timezone.now().date()
    return AiRequestLog.objects.filter(subsystem=subsystem, created_at__date=today).count()


def invoke(
    subsystem,
    user,
    module_code: str,
    prompt: str,
    handler: Callable[[], str],
    *,
    meta: dict | None = None,
) -> str:
    """Проверяет политику, выполняет handler, пишет AiRequestLog."""
    from delayu.services.ai import get_or_create_policy

    policy = get_or_create_policy(subsystem)
    if _usage_today(subsystem) >= policy.max_requests_per_day:
        raise AiGatewayError("limit_exceeded", "Дневной лимит запросов ИИ исчерпан")

    safe_prompt = prompt
    pii_redacted = False
    if not policy.allow_pii and contains_pii(prompt):
        safe_prompt = redact_pii(prompt)
        pii_redacted = True

    started = time.monotonic()
    response = ""
    error = ""
    try:
        response = handler()
    except Exception as exc:  # noqa: BLE001 — gateway must log failures
        error = str(exc)[:500]
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        log_meta = {
            "gateway": "1.0",
            "latency_ms": latency_ms,
            "pii_redacted": pii_redacted,
            "model": policy.model_name,
        }
        if meta:
            log_meta.update(meta)
        if error:
            log_meta["error"] = error
        AiRequestLog.objects.create(
            subsystem=subsystem,
            module_code=module_code,
            user=user,
            prompt=safe_prompt[:8000],
            response=response[:8000] if response else "",
            meta=log_meta,
        )
    return response
