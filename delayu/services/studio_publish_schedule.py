"""Отложенная публикация черновика Студии (без Celery)."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from delayu.models import Subsystem

_SCHEDULE_KEY = "scheduled_publish"


def get_scheduled_publish(subsystem) -> dict | None:
    if subsystem.pk:
        from delayu.models import Subsystem

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


def set_scheduled_publish(
    subsystem,
    at,
    *,
    comment: str = "",
    user_id: int | None = None,
    tags: list | None = None,
) -> dict:
    if at <= timezone.now():
        raise ValueError("Время публикации должно быть в будущем")
    if not subsystem.studio_has_draft:
        raise ValueError("Нет черновика для публикации")
    cleaned_tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    state = dict(subsystem.studio_setup_state or {})
    state[_SCHEDULE_KEY] = {
        "at": at.isoformat(),
        "comment": (comment or "")[:255],
        "user_id": user_id,
        "tags": cleaned_tags,
    }
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return state[_SCHEDULE_KEY]


def preview_schedule_publish(
    subsystem,
    at,
    *,
    comment: str = "",
    tags: list | None = None,
) -> dict:
    """Dry-run перед отложенной публикацией: diff черновика + проверка времени."""
    from delayu.services.studio_admin import dry_run_publish, preview_publish_tags

    if at <= timezone.now():
        raise ValueError("Время публикации должно быть в будущем")
    if not subsystem.studio_has_draft:
        raise ValueError("Нет черновика для публикации")
    preview = dry_run_publish(subsystem, tags=tags)
    if not preview.get("ok"):
        return preview
    cleaned_tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    preview["schedule_preview"] = True
    preview["scheduled_at"] = at.isoformat()
    preview["schedule_comment"] = (comment or "")[:255]
    preview["schedule_tags"] = cleaned_tags
    preview["schedule_publish_tags"] = preview_publish_tags(subsystem, cleaned_tags)["merged"]
    preview["existing_schedule"] = get_scheduled_publish(subsystem)
    return preview


def cancel_scheduled_publish(subsystem) -> bool:
    state = dict(subsystem.studio_setup_state or {})
    if _SCHEDULE_KEY not in state:
        return False
    state.pop(_SCHEDULE_KEY, None)
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return True


def _parse_schedule_at(raw: str):
    at = parse_datetime(raw or "")
    if at is None:
        return None
    if timezone.is_naive(at):
        at = timezone.make_aware(at, timezone.get_current_timezone())
    return at


def process_due_scheduled_publishes(*, limit: int = 20) -> dict:
    """Опубликовать черновики, у которых наступило запланированное время."""
    from delayu.services.studio_admin import publish_studio_draft

    User = get_user_model()
    now = timezone.now()
    published = []
    errors = []
    for sub in Subsystem.objects.filter(status=Subsystem.Status.ACTIVE):
        sched = get_scheduled_publish(sub)
        if not sched:
            continue
        at = _parse_schedule_at(sched.get("at", ""))
        if at is None or at > now:
            continue
        if not sub.studio_has_draft:
            cancel_scheduled_publish(sub)
            errors.append({"code": sub.code, "error": "no_draft"})
        else:
            user = User.objects.filter(pk=sched.get("user_id")).first()
            if not user:
                cancel_scheduled_publish(sub)
                errors.append({"code": sub.code, "error": "no_user"})
            else:
                sched_tags = sched.get("tags")
                explicit_tags = sched_tags if isinstance(sched_tags, list) else None
                revision = publish_studio_draft(
                    sub,
                    user,
                    comment=sched.get("comment") or "По расписанию",
                    tags=explicit_tags,
                )
                cancel_scheduled_publish(sub)
                _notify_scheduled_publish(user, sub, revision, sched)
                published.append(sub.code)
        if len(published) + len(errors) >= limit:
            break
    return {"published": published, "errors": errors, "count": len(published)}


def _notify_scheduled_publish(user, subsystem, revision, sched: dict) -> None:
    """In-app, e-mail и SMS/Telegram по шаблонам M78 или fallback."""
    from delayu.models import Notification, NotificationTemplate
    from delayu.services import audit
    from delayu.services.mail import send_mail_message
    from delayu.services.notify_dispatch import dispatch_event

    version = revision.version_label if revision else subsystem.config_version
    comment = (sched.get("comment") or "").strip()
    body = comment or "Черновик меню/СЭД опубликован по расписанию."
    title = f"Студия: опубликована {version}"
    link = "/studio/"
    ctx = {
        "version": version,
        "comment": body,
        "link": link,
        "subsystem": subsystem.name,
    }
    has_templates = NotificationTemplate.objects.filter(
        subsystem=subsystem,
        event_code="studio_scheduled_publish",
        is_active=True,
    ).exists()
    if has_templates:
        dispatch_event(subsystem, "studio_scheduled_publish", [user], ctx)
    else:
        Notification.objects.create(
            user=user,
            subsystem=subsystem,
            title=title,
            body=body,
            link=link,
            level=Notification.Level.INFO,
        )
        if user.email:
            send_mail_message(
                subsystem=subsystem,
                to_addrs=[user.email],
                subject=title,
                body=f"{body}\n\nПодсистема: {subsystem.name}\n{link}",
                event_code="studio_scheduled_publish",
            )
        from delayu.services.notify_dispatch import _send_sms_template

        _send_sms_template(
            user,
            subsystem,
            subject=title,
            body=f"{body}\n{link}",
            event_code="studio_scheduled_publish",
        )
    audit.log_action(
        user,
        subsystem,
        "studio.scheduled_publish_done",
        "StudioConfigRevision",
        revision.pk if revision else "",
        payload={"version": version, "comment": comment},
    )
