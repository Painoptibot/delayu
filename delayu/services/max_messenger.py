"""MAX / мессенджеры (M41) — HTTP API или журнал исходящих."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from delayu.models import MailDeliveryLog, MessengerChannel


def get_max_channel(subsystem):
    return (
        MessengerChannel.objects.filter(
            subsystem=subsystem,
            channel_type=MessengerChannel.ChannelType.MAX,
            is_active=True,
        )
        .order_by("code")
        .first()
    )


def send_max_message(subsystem, recipient: str, text: str, *, event_code: str = "") -> bool:
    """
    Демо: запись в журнал доставки. Для продакшена укажите webhook_url с API MAX в канале.
    """
    recipient = (recipient or "").strip()
    if not recipient:
        return False
    channel = get_max_channel(subsystem)
    if not channel:
        return False
    api_url = (channel.webhook_url or "").strip()
    success = True
    err = text[:2000]
    if api_url and not api_url.startswith("demo:"):
        body = json.dumps(
            {"recipient": recipient, "text": text, "event_code": event_code},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            api_url,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "Delayu-MAX/1.0"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                success = 200 <= resp.status < 300
                err = (resp.read(500) or b"").decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            success = False
            err = f"HTTP {exc.code}: {exc.read(300).decode('utf-8', errors='replace')}"
        except OSError as exc:
            success = False
            err = str(exc)[:500]
    MailDeliveryLog.objects.create(
        subsystem=subsystem,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient=f"max:{recipient}"[:255],
        subject=(text.split("\n", 1)[0])[:500],
        event_code=(event_code or "max")[:64],
        success=success,
        error_message=err,
    )
    return success
