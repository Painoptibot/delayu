"""#36 — журнал доставки уведомлений (SMTP/Telegram)."""
from django.db.models import Q
from django.utils import timezone

from delayu.models import MailDeliveryLog


def filter_delivery_logs(subsystem, params=None):
    params = params or {}
    qs = MailDeliveryLog.objects.filter(subsystem=subsystem)
    if params.get("success") == "1":
        qs = qs.filter(success=True)
    elif params.get("success") == "0":
        qs = qs.filter(success=False)
    direction = (params.get("direction") or "").strip()
    if direction:
        qs = qs.filter(direction=direction)
    event = (params.get("event_code") or "").strip()
    if event:
        qs = qs.filter(event_code__icontains=event)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(recipient__icontains=q)
            | Q(subject__icontains=q)
            | Q(error_message__icontains=q)
        )
    return qs.order_by("-created_at")


def delivery_metrics(subsystem):
    qs = MailDeliveryLog.objects.filter(subsystem=subsystem)
    today = qs.filter(created_at__date=timezone.now().date())
    return {
        "total": qs.count(),
        "failed": qs.filter(success=False).count(),
        "outbound_today": today.filter(direction=MailDeliveryLog.Direction.OUTBOUND).count(),
        "inbound_today": today.filter(direction=MailDeliveryLog.Direction.INBOUND).count(),
    }


def serialize_log(log: MailDeliveryLog) -> dict:
    return {
        "id": log.pk,
        "direction": log.direction,
        "recipient": log.recipient,
        "sender": log.sender,
        "subject": log.subject,
        "event_code": log.event_code,
        "success": log.success,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat(),
    }
