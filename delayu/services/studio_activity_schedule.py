"""Автоматическая рассылка сводки активности Студии (cron / run_scheduled_tasks)."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from delayu.models import Subsystem

_SCHEDULE_KEY = "activity_digest_schedule"


def get_activity_digest_schedule(subsystem) -> dict | None:
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


def set_activity_digest_schedule(
    subsystem,
    *,
    enabled: bool = True,
    interval_days: int = 7,
    digest_days: int = 7,
) -> dict:
    interval_days = max(1, min(int(interval_days or 7), 90))
    digest_days = max(1, min(int(digest_days or 7), 90))
    state = dict(subsystem.studio_setup_state or {})
    prev = state.get(_SCHEDULE_KEY) or {}
    state[_SCHEDULE_KEY] = {
        "enabled": bool(enabled),
        "interval_days": interval_days,
        "digest_days": digest_days,
        "last_sent_at": prev.get("last_sent_at"),
    }
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return state[_SCHEDULE_KEY]


def _parse_iso(raw: str):
    at = parse_datetime(raw or "")
    if at is None:
        return None
    if timezone.is_naive(at):
        at = timezone.make_aware(at, timezone.get_current_timezone())
    return at


def process_due_studio_activity_digests(*, limit: int = 20) -> dict:
    """Разослать digest администраторам, если наступил интервал."""
    from delayu.services.audit import log_action
    from delayu.services.studio_activity import notify_studio_activity_digest_admins

    now = timezone.now()
    sent = []
    for sub in Subsystem.objects.filter(status=Subsystem.Status.ACTIVE):
        sched = get_activity_digest_schedule(sub)
        if not sched or not sched.get("enabled"):
            continue
        interval = max(1, int(sched.get("interval_days") or 7))
        digest_days = max(1, int(sched.get("digest_days") or 7))
        last_at = _parse_iso(sched.get("last_sent_at") or "")
        if last_at and now < last_at + timedelta(days=interval):
            continue
        count = notify_studio_activity_digest_admins(sub, days=digest_days)
        state = dict(sub.studio_setup_state or {})
        entry = dict(state.get(_SCHEDULE_KEY) or {})
        entry["last_sent_at"] = now.isoformat()
        state[_SCHEDULE_KEY] = entry
        sub.studio_setup_state = state
        sub.save(update_fields=["studio_setup_state", "updated_at"])
        log_action(
            None,
            sub,
            "studio.activity_digest_auto",
            "Subsystem",
            sub.pk,
            payload={"days": digest_days, "notified": count, "interval_days": interval},
        )
        sent.append({"code": sub.code, "notified": count})
        if len(sent) >= limit:
            break
    return {"sent": sent, "count": len(sent)}
