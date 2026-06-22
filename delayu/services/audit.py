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


def filter_audit_logs(
    subsystem, *, action: str = "", date_from=None, date_to=None, limit: int = 5000, forced_only: bool = False
):
    qs = AuditLog.objects.filter(subsystem=subsystem).select_related("user")
    action = (action or "").strip()
    if action:
        qs = qs.filter(action__icontains=action)
    if forced_only:
        qs = qs.filter(payload__forced=True)
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


def export_audit_csv(
    subsystem, *, action: str = "", mask_pii: bool = False, forced_only: bool = False
) -> HttpResponse:
    rows = filter_audit_logs(subsystem, action=action, forced_only=forced_only)
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


def export_studio_audit_csv(
    subsystem,
    *,
    action: str = "studio.",
    mask_pii: bool = False,
    forced_only: bool = False,
    revision_tag: str = "",
) -> HttpResponse:
    """Экспорт записей журнала аудита с действиями studio.* (или конкретным action)."""
    from delayu.services import studio_admin

    prefix = (action or "studio.").strip() or "studio."
    rows = filter_audit_logs(subsystem, action=prefix, forced_only=forced_only)
    if revision_tag:
        rows = studio_admin.filter_studio_audit_by_revision_tag(rows, subsystem, revision_tag)
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
    stamp = timezone.localtime().strftime("%Y%m%d")
    suffix = "-forced" if forced_only else ""
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-audit{suffix}-{subsystem.code}-{stamp}.csv"'
    )
    return resp


def export_studio_forced_audit_csv(subsystem, *, mask_pii: bool = False) -> HttpResponse:
    """CSV журнала принудительных импортов и откатов (payload.forced=true)."""
    rows = (
        AuditLog.objects.filter(
            subsystem=subsystem,
            action__in=("studio.import", "studio.restore"),
        )
        .filter(payload__forced=True)
        .select_related("user")
        .order_by("-created_at")[:5000]
    )
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
    stamp = timezone.localtime().strftime("%Y%m%d")
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-forced-{subsystem.code}-{stamp}.csv"'
    )
    return resp


def export_studio_compliance_package(
    subsystem,
    *,
    mask_pii: bool = False,
    revision_tag: str = "",
) -> HttpResponse:
    """ZIP: пакет конфигурации + журналы studio.* + реестр ревизий."""
    import zipfile

    from delayu.models import StudioConfigRevision
    from delayu.services import studio_admin

    tag_filter = (revision_tag or "").strip()
    package = studio_admin.export_config_package(subsystem)
    audit_csv = export_studio_audit_csv(subsystem, mask_pii=mask_pii)
    forced_csv = export_studio_forced_audit_csv(subsystem, mask_pii=mask_pii)
    activity_days = 7
    activity_csv = export_studio_activity_digest_csv(
        subsystem, days=activity_days, mask_pii=mask_pii
    )
    rev_qs = StudioConfigRevision.objects.filter(subsystem=subsystem).order_by("-created_at")
    if tag_filter:
        tag_ids = studio_admin.get_revision_ids_by_tag(subsystem, tag_filter)
        rev_qs = rev_qs.filter(pk__in=tag_ids) if tag_ids else rev_qs.none()
    revisions = list(rev_qs.values("id", "version_label", "comment", "created_at")[:500])
    tag_map = studio_admin.get_revision_tags_map(subsystem)
    pinned_ids = studio_admin.get_pinned_revision_ids(subsystem)
    for row in revisions:
        row["created_at"] = (
            timezone.localtime(row["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
            if row.get("created_at")
            else ""
        )
        row["tags"] = tag_map.get(row["id"], [])
        row["pinned"] = row["id"] in pinned_ids
    revision_meta = {
        "pinned_revision_ids": pinned_ids,
        "revision_tags": {str(k): v for k, v in tag_map.items()},
        "tag_index": studio_admin.list_revision_tags(subsystem),
    }
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "config.json",
            json.dumps(package, ensure_ascii=False, indent=2),
        )
        zf.writestr("studio-audit.csv", audit_csv.content)
        zf.writestr("studio-forced-audit.csv", forced_csv.content)
        zf.writestr("studio-activity.csv", activity_csv.content)
        zf.writestr(
            "revisions.json",
            json.dumps(revisions, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "revision-meta.json",
            json.dumps(revision_meta, ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "delayu-studio-compliance",
                    "format_version": 4,
                    "exported_at": timezone.now().isoformat(),
                    "subsystem": subsystem.code,
                    "config_version": subsystem.config_version or "",
                    "mask_pii": mask_pii,
                    "revision_count": len(revisions),
                    "activity_days": activity_days,
                    "pinned_revisions": len(pinned_ids),
                    "tag_count": len(revision_meta["tag_index"]),
                    "revision_tag_filter": tag_filter or None,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-compliance-{subsystem.code}-{stamp}.zip"'
    )
    return resp


def export_revision_compare_csv(
    subsystem,
    result: dict,
    *,
    rev_a: str = "",
    rev_b: str = "",
) -> HttpResponse:
    """CSV детального сравнения ревизий (секции, формы, BPM)."""
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["compare_a", rev_a, "compare_b", rev_b])
    writer.writerow(["kind", "key", "code", "change", "detail"])
    for section in result.get("sections") or []:
        writer.writerow(
            [
                "section",
                section.get("key") or "",
                "",
                "",
                section.get("detail") or "",
            ]
        )
    entity = result.get("entity_diffs") or {}
    for form in entity.get("forms") or []:
        detail = ""
        if form.get("detail"):
            d = form["detail"]
            detail = f"+{len(d.get('added') or [])}/−{len(d.get('removed') or [])}/~{len(d.get('changed') or [])}"
        writer.writerow(["form", "", form.get("code") or "", form.get("change") or "", detail])
    for bpm in entity.get("bpm") or []:
        detail = ""
        if bpm.get("detail"):
            d = bpm["detail"]
            detail = f"+{len(d.get('added') or [])}/−{len(d.get('removed') or [])}/~{len(d.get('changed') or [])}"
        writer.writerow(["bpm", "", bpm.get("code") or "", bpm.get("change") or "", detail])
    for row in (result.get("policies_diff") or {}).get("changed") or []:
        writer.writerow(
            [
                "policy",
                row.get("attr") or "",
                "",
                "changed",
                f"{row.get('before')} → {row.get('after')}",
            ]
        )
    stamp = timezone.localtime().strftime("%Y%m%d")
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-compare-{subsystem.code}-{stamp}.csv"'
    )
    return resp


def export_studio_activity_digest_csv(
    subsystem, *, days: int = 7, limit: int = 200, mask_pii: bool = False
) -> HttpResponse:
    """CSV активности Студии за период."""
    from delayu.services.studio_activity import build_studio_activity_digest

    digest = build_studio_activity_digest(subsystem, days=days, limit=limit)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["period_days", digest["days"], "total", digest["total"], "forced", digest["forced_count"]])
    writer.writerow([])
    writer.writerow(["created_at", "user", "action", "detail", "forced"])
    for entry in digest.get("entries") or []:
        writer.writerow(
            [
                entry.get("at") or "",
                entry.get("user") or "",
                entry.get("action") or "",
                entry.get("detail") or "",
                "yes" if entry.get("forced") else "no",
            ]
        )
    stamp = timezone.localtime().strftime("%Y%m%d")
    resp = HttpResponse(buf.getvalue().encode("utf-8-sig"), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-activity-{subsystem.code}-{stamp}.csv"'
    )
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