"""Отправка сообщений через Telegram Bot API (M41)."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from delayu.models import MailDeliveryLog, MessengerChannel


def _telegram_api_base(channel: MessengerChannel) -> str | None:
    from django.conf import settings

    token = (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()
    if token and token != "demo":
        return f"https://api.telegram.org/bot{token}"
    url = (channel.webhook_url or "").strip()
    if not url:
        return None
    match = re.match(r"(https://api\.telegram\.org/bot[^/]+)", url)
    return match.group(1) if match else None


def get_telegram_channel(subsystem):
    return (
        MessengerChannel.objects.filter(
            subsystem=subsystem,
            channel_type=MessengerChannel.ChannelType.TELEGRAM,
            is_active=True,
        )
        .order_by("code")
        .first()
    )


def _log_delivery(
    subsystem,
    *,
    recipient: str,
    subject: str,
    body: str,
    event_code: str,
    success: bool,
    error_message: str = "",
):
    MailDeliveryLog.objects.create(
        subsystem=subsystem,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient=recipient[:255],
        subject=subject[:500],
        event_code=event_code[:64],
        success=success,
        error_message=(error_message or body)[:2000],
    )


def normalize_telegram_chat_id(recipient: str) -> str:
    recipient = (recipient or "").strip()
    if not recipient:
        return ""
    numeric = recipient.lstrip("-")
    if numeric.isdigit():
        return recipient
    if recipient.startswith("@"):
        return recipient
    return f"@{recipient.lstrip('@')}"


def send_telegram_message(
    subsystem, recipient: str, text: str, *, event_code: str = ""
) -> bool:
    """
    POST sendMessage через настроенный MessengerChannel подсистемы.
    recipient: @username или numeric chat_id из профиля пользователя.
    При отсутствии канала или demo-токена — False (вызывающий код делает fallback).
    """
    recipient = (recipient or "").strip()
    if not recipient:
        return False

    channel = get_telegram_channel(subsystem)
    if not channel:
        return False

    base = _telegram_api_base(channel)
    if not base or base.endswith("/bot/demo"):
        from django.conf import settings

        if getattr(settings, "DELAYU_TELEGRAM_DEMO_LOG", False):
            _log_delivery(
                subsystem,
                recipient=f"telegram:{recipient}",
                subject=text.split("\n", 1)[0][:500],
                body=text,
                event_code=event_code or "telegram_demo",
                success=True,
                error_message="[demo] TELEGRAM_BOT_TOKEN не задан — запись в журнал",
            )
            return True
        return False

    chat_id = normalize_telegram_chat_id(recipient)
    if not chat_id:
        return False
    payload = json.dumps({"chat_id": chat_id, "text": text[:4096]}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    code = event_code or "telegram"
    subject = text.split("\n", 1)[0][:500]
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            ok = 200 <= resp.status < 300
        _log_delivery(
            subsystem,
            recipient=f"telegram:{recipient}",
            subject=subject,
            body=text,
            event_code=code,
            success=ok,
        )
        return ok
    except urllib.error.URLError as exc:
        _log_delivery(
            subsystem,
            recipient=f"telegram:{recipient}",
            subject=subject,
            body=text,
            event_code=code,
            success=False,
            error_message=str(exc),
        )
        return False
