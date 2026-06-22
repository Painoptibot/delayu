"""Плановый экспорт compliance-пакета Студии на диск (cron)."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from delayu.models import Subsystem

_SCHEDULE_KEY = "compliance_export_schedule"


def compliance_export_dir() -> Path:
    base = Path(getattr(settings, "MEDIA_ROOT", settings.BASE_DIR / "media"))
    path = base / "studio_compliance_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_compliance_export_schedule(subsystem) -> dict | None:
    if subsystem.pk:
        state = (
            Subsystem.objects.filter(pk=subsystem.pk)
            .values_list("studio_setup_state", flat=True)
            .first()
            or {}
        )
    else:
        state = subsystem.studio_setup_state or {}
    sched = state.get(_SCHEDULE_KEY)
    return dict(sched) if sched else None


def set_compliance_export_schedule(
    subsystem,
    *,
    enabled: bool = True,
    interval_days: int = 30,
    mask_pii: bool = False,
    revision_tag: str = "",
) -> dict:
    interval_days = max(1, min(int(interval_days or 30), 365))
    tag = (revision_tag or "").strip()
    state = dict(subsystem.studio_setup_state or {})
    prev = state.get(_SCHEDULE_KEY) or {}
    state[_SCHEDULE_KEY] = {
        "enabled": bool(enabled),
        "interval_days": interval_days,
        "mask_pii": bool(mask_pii),
        "revision_tag": tag,
        "last_export_at": prev.get("last_export_at"),
        "last_export_file": prev.get("last_export_file"),
    }
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return state[_SCHEDULE_KEY]


def save_studio_compliance_snapshot(
    subsystem,
    *,
    mask_pii: bool = False,
    revision_tag: str = "",
) -> dict:
    """Сохранить compliance ZIP на диск."""
    from delayu.services.audit import export_studio_compliance_package

    tag = (revision_tag or "").strip()
    resp = export_studio_compliance_package(
        subsystem, mask_pii=mask_pii, revision_tag=tag
    )
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    suffix = "_pii_masked" if mask_pii else ""
    filename = f"studio-compliance_{subsystem.code}_{stamp}{suffix}.zip"
    filepath = compliance_export_dir() / filename
    filepath.write_bytes(resp.content)
    result = {
        "path": str(filepath),
        "filename": filename,
        "size": len(resp.content),
        "subsystem": subsystem.code,
        "mask_pii": mask_pii,
        "revision_tag": tag or None,
    }
    from delayu.services.studio_publish_events import on_studio_compliance_exported

    on_studio_compliance_exported(
        subsystem,
        None,
        filename=filename,
        size=result["size"],
        source="auto",
        mask_pii=mask_pii,
        revision_tag=tag,
    )
    return result


def _parse_iso(raw: str):
    at = parse_datetime(raw or "")
    if at is None:
        return None
    if timezone.is_naive(at):
        at = timezone.make_aware(at, timezone.get_current_timezone())
    return at


def process_due_studio_compliance_exports(*, limit: int = 10) -> dict:
    """Экспорт compliance ZIP по расписанию."""
    from delayu.services.audit import log_action

    now = timezone.now()
    exported = []
    for sub in Subsystem.objects.filter(status=Subsystem.Status.ACTIVE):
        sched = get_compliance_export_schedule(sub)
        if not sched or not sched.get("enabled"):
            continue
        interval = max(1, int(sched.get("interval_days") or 30))
        last_at = _parse_iso(sched.get("last_export_at") or "")
        if last_at and now < last_at + timedelta(days=interval):
            continue
        mask_pii = bool(sched.get("mask_pii"))
        revision_tag = (sched.get("revision_tag") or "").strip()
        result = save_studio_compliance_snapshot(
            sub, mask_pii=mask_pii, revision_tag=revision_tag
        )
        state = dict(sub.studio_setup_state or {})
        entry = dict(state.get(_SCHEDULE_KEY) or {})
        entry["last_export_at"] = now.isoformat()
        entry["last_export_file"] = result["filename"]
        state[_SCHEDULE_KEY] = entry
        sub.studio_setup_state = state
        sub.save(update_fields=["studio_setup_state", "updated_at"])
        log_action(
            None,
            sub,
            "studio.compliance_export_auto",
            "Subsystem",
            sub.pk,
            payload={
                "filename": result["filename"],
                "size": result["size"],
                "mask_pii": mask_pii,
            },
        )
        exported.append({"code": sub.code, "filename": result["filename"]})
        if len(exported) >= limit:
            break
    return {"exported": exported, "count": len(exported)}
