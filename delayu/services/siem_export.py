"""Экспорт журнала аудита в SIEM через webhook (#56)."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from django.utils import timezone

from delayu.models import AuditLog, SiemExportConfig


def get_or_create_siem_config(subsystem) -> SiemExportConfig:
    cfg, _ = SiemExportConfig.objects.get_or_create(subsystem=subsystem)
    return cfg


def _severity_for_action(action: str) -> str:
    action = (action or "").lower()
    if any(x in action for x in ("delete", "purge", "reject", "fail", "denied")):
        return "high"
    if any(x in action for x in ("login", "auth", "permission", "role", "export")):
        return "medium"
    return "low"


def build_siem_payload(subsystem, *, since=None, limit: int = 500) -> list[dict]:
    qs = AuditLog.objects.filter(subsystem=subsystem).select_related("user").order_by(
        "created_at"
    )
    if since:
        qs = qs.filter(created_at__gt=since)
    events = []
    for row in qs[:limit]:
        events.append(
            {
                "timestamp": row.created_at.isoformat(),
                "subsystem": subsystem.code,
                "action": row.action,
                "severity": _severity_for_action(row.action),
                "user": row.user.username if row.user_id else "",
                "model": row.model_name,
                "object_id": row.object_id,
                "ip": row.ip_address or "",
                "payload": row.payload or {},
            }
        )
    return events


def push_siem_events(subsystem, *, limit: int = 500) -> dict:
    cfg = get_or_create_siem_config(subsystem)
    if not cfg.enabled or not cfg.webhook_url:
        return {"ok": False, "skipped": True, "reason": "disabled"}
    events = build_siem_payload(subsystem, since=cfg.last_pushed_at, limit=limit)
    if not events:
        return {"ok": True, "pushed": 0}
    body = json.dumps(
        {
            "source": "delayu",
            "subsystem": subsystem.code,
            "exported_at": timezone.now().isoformat(),
            "events": events,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        cfg.webhook_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                raise urllib.error.HTTPError(
                    cfg.webhook_url, resp.status, resp.reason, resp.headers, None
                )
    except Exception as exc:
        cfg.last_error = str(exc)[:500]
        cfg.save(update_fields=["last_error"])
        return {"ok": False, "error": cfg.last_error, "pushed": 0}
    cfg.last_pushed_at = timezone.now()
    cfg.last_error = ""
    cfg.save(update_fields=["last_pushed_at", "last_error"])
    return {"ok": True, "pushed": len(events)}
