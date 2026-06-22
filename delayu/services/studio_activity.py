"""Сводка активности Студии для hub и compliance."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from delayu.models import AuditLog


def build_studio_activity_digest(subsystem, *, days: int = 7, limit: int = 30) -> dict:
    """Журнал действий studio.* за последние N дней."""
    days = max(1, min(int(days or 7), 90))
    limit = max(1, min(int(limit or 30), 200))
    since = timezone.now() - timedelta(days=days)
    base_qs = AuditLog.objects.filter(
        subsystem=subsystem,
        action__startswith="studio.",
        created_at__gte=since,
    )
    from django.db.models import Count

    by_action_rows = base_qs.values("action").annotate(count=Count("id")).order_by("-count")
    by_action = {row["action"]: row["count"] for row in by_action_rows}
    entries = list(
        base_qs.select_related("user").order_by("-created_at")[:limit]
    )
    forced_count = base_qs.filter(payload__forced=True).count()
    return {
        "ok": True,
        "days": days,
        "since": since.isoformat(),
        "total": base_qs.count(),
        "forced_count": forced_count,
        "by_action": [
            {"action": action, "count": count}
            for action, count in sorted(by_action.items(), key=lambda x: (-x[1], x[0]))
        ],
        "entries": [
            {
                "at": timezone.localtime(entry.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                "user": entry.user.get_username() if entry.user_id else "",
                "action": entry.action,
                "detail": _entry_detail(entry),
                "forced": bool((entry.payload or {}).get("forced")),
            }
            for entry in entries
        ],
    }


def _entry_detail(entry) -> str:
    payload = entry.payload or {}
    if payload.get("version"):
        return f"v{payload['version']}"
    if payload.get("from"):
        return f"← {payload['from']}"
    if payload.get("blueprint"):
        return str(payload["blueprint"])
    if payload.get("stats"):
        stats = payload["stats"]
        if isinstance(stats, dict):
            parts = [f"{k}={v}" for k, v in stats.items() if v][:3]
            return ", ".join(parts)
    if payload.get("changed_sections") is not None:
        return f"блоков: {payload['changed_sections']}"
    return ""


def format_digest_summary(digest: dict, *, max_lines: int = 8) -> str:
    """Текстовая сводка для e-mail / in-app."""
    lines = []
    for row in (digest.get("by_action") or [])[:max_lines]:
        lines.append(f"• {row['action']}: {row['count']}")
    for entry in (digest.get("entries") or [])[:max_lines]:
        line = f"• {entry.get('at')} {entry.get('action')}"
        if entry.get("detail"):
            line += f" ({entry['detail']})"
        if entry.get("forced"):
            line += " [forced]"
        lines.append(line)
    return "\n".join(lines) or "Нет событий за период."


ACTIVITY_DIGEST_EVENT = "studio.activity_digest"


def emit_studio_activity_digest_webhook(subsystem, digest: dict, *, notified: int) -> int:
    """Webhook studio.activity_digest после рассылки сводки."""
    from delayu.services.integration_events import emit_integration_event

    data = {
        "external_id": f"studio-digest:{subsystem.code}:{digest.get('days', 7)}",
        "days": digest.get("days", 7),
        "total": digest.get("total", 0),
        "forced_count": digest.get("forced_count", 0),
        "notified": notified,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, ACTIVITY_DIGEST_EVENT, data)


def notify_studio_activity_digest_admins(subsystem, *, days: int = 7) -> int:
    """In-app/e-mail администраторам: сводка активности Студии."""
    from delayu.models import Notification, NotificationTemplate
    from delayu.services.notify_dispatch import dispatch_event
    from delayu.services.studio_forced_import import _subsystem_admins

    digest = build_studio_activity_digest(subsystem, days=days, limit=20)
    if digest["total"] <= 0:
        return 0
    admins = list(_subsystem_admins(subsystem))
    if not admins:
        return 0
    ctx = {
        "subsystem": subsystem.name,
        "days": digest["days"],
        "total": digest["total"],
        "forced_count": digest["forced_count"],
        "summary": format_digest_summary(digest),
        "link": "/studio/",
    }
    if NotificationTemplate.objects.filter(
        subsystem=subsystem,
        event_code=ACTIVITY_DIGEST_EVENT,
        is_active=True,
    ).exists():
        dispatch_event(subsystem, ACTIVITY_DIGEST_EVENT, admins, ctx)
        emit_studio_activity_digest_webhook(subsystem, digest, notified=len(admins))
        return len(admins)
    title = f"Студия: сводка за {digest['days']} дн."
    body = ctx["summary"][:2000]
    for admin in admins:
        Notification.objects.create(
            user=admin,
            subsystem=subsystem,
            title=title[:255],
            body=body,
            link="/studio/",
        )
    emit_studio_activity_digest_webhook(subsystem, digest, notified=len(admins))
    return len(admins)
