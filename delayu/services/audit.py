"""Append-only audit log + экспорт и снимки для compliance."""
import csv
import io
import json
import re
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from delayu.models import AuditLog
_PII_KEYS = re.compile(r"(email|phone|passport|snils|inn|address|ip)", re.I)


def log_action(user, subsystem, action, model_name="", object_id="", payload=None, request=None):
    ip = None
    if request:
        ip = request.META.get("REMOTE_ADDR")
    AuditLog.objects.create(
        user=user,
        subsystem=subsystem,
        action=action,
        model_name=model_name,
        object_id=str(object_id),
        payload=payload or {},
        ip_address=ip,
    )


def filter_audit_logs(subsystem, *, action: str = "", date_from=None, date_to=None, limit: int = 5000):
    qs = AuditLog.objects.filter(subsystem=subsystem).select_related("user")
    action = (action or "").strip()
    if action:
        qs = qs.filter(action__icontains=action)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs.order_by("-created_at")[:limit]


def _mask_ip(ip: str | None) -> str:
    if not ip:
        return ""
    if ":" in ip:
        parts = ip.split(":")
        if len(parts) > 1:
            parts[-1] = "****"
            return ":".join(parts)
        return ip
    parts = ip.split(".")
    if len(parts) == 4:
        parts[-1] = "xxx"
        return ".".join(parts)
    return ip


def _mask_payload(payload: dict) -> dict:
    if not payload:
        return {}
    masked = {}
    for key, value in payload.items():
        if _PII_KEYS.search(str(key)):
            masked[key] = "***"
        elif isinstance(value, dict):
            masked[key] = _mask_payload(value)
        else:
            masked[key] = value
    return masked


def export_audit_csv(subsystem, *, action: str = "", mask_pii: bool = False) -> HttpResponse:
    rows = filter_audit_logs(subsystem, action=action)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(
        [
            "created_at",
            "user",
            "action",
            "model_name",
            "object_id",
            "ip_address",
            "payload",
        ]
    )
    for entry in rows:
        user_label = ""
        if entry.user_id:
            user_label = entry.user.get_username()
        ip = _mask_ip(str(entry.ip_address)) if mask_pii else (entry.ip_address or "")
        payload = entry.payload or {}
        if mask_pii:
            payload = _mask_payload(payload)
        writer.writerow(
            [
                timezone.localtime(entry.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                user_label,
                entry.action,
                entry.model_name,
                entry.object_id,
                ip,
                json.dumps(payload, ensure_ascii=False),
            ]
        )
    stamp = timezone.localtime().strftime("%Y%m%d")
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="audit-{subsystem.code}-{stamp}.csv"'
    return resp


def audit_export_dir() -> Path:
    base = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR / "media"))
    path = base / "audit_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_audit_snapshot(subsystem, *, action: str = "", mask_pii: bool = False) -> dict:
    """Сохранить CSV-снимок журнала аудита на диск (для cron / compliance)."""
    rows = filter_audit_logs(subsystem, action=action)
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    suffix = "_pii_masked" if mask_pii else ""
    filename = f"audit_{subsystem.code}_{stamp}{suffix}.csv"
    filepath = audit_export_dir() / filename
    with filepath.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow(
            ["created_at", "user", "action", "model_name", "object_id", "ip_address", "payload"]
        )
        row_count = 0
        for entry in rows:
            row_count += 1
            user_label = entry.user.get_username() if entry.user_id else ""
            ip = _mask_ip(str(entry.ip_address)) if mask_pii else (entry.ip_address or "")
            payload = entry.payload or {}
            if mask_pii:
                payload = _mask_payload(payload)
            writer.writerow(
                [
                    timezone.localtime(entry.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    user_label,
                    entry.action,
                    entry.model_name,
                    entry.object_id,
                    ip,
                    json.dumps(payload, ensure_ascii=False),
                ]
            )
    return {
        "path": str(filepath),
        "filename": filename,
        "rows": row_count,
        "subsystem": subsystem.code,
        "mask_pii": mask_pii,
    }


def list_audit_snapshots(*, subsystem_code: str = "", limit: int = 20) -> list[dict]:
    directory = audit_export_dir()
    files = sorted(directory.glob("audit_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    if subsystem_code:
        prefix = f"audit_{subsystem_code}_"
        files = [p for p in files if p.name.startswith(prefix)]
    result = []
    for path in files[:limit]:
        stat = path.stat()
        result.append(
            {
                "filename": path.name,
                "size": stat.st_size,
                "modified": timezone.datetime.fromtimestamp(stat.st_mtime, tz=timezone.get_current_timezone()),
            }
        )
    return result