"""Журнал сессий и отзыв (#14)."""
from django.contrib.sessions.models import Session
from django.utils import timezone

from delayu.models import UserSession


def _ua_label(user_agent: str) -> str:
    ua = (user_agent or "").lower()
    if "edg/" in ua:
        return "Microsoft Edge"
    if "chrome/" in ua and "chromium" not in ua:
        return "Google Chrome"
    if "firefox/" in ua:
        return "Mozilla Firefox"
    if "safari/" in ua and "chrome" not in ua:
        return "Safari"
    return "Веб-клиент «ДелаЮ»"


def register_session(request) -> UserSession | None:
    if not request.user.is_authenticated:
        return None
    key = request.session.session_key
    if not key:
        request.session.save()
        key = request.session.session_key
    ip = request.META.get("REMOTE_ADDR")
    ua = (request.META.get("HTTP_USER_AGENT") or "")[:400]
    row, _created = UserSession.objects.update_or_create(
        session_key=key,
        defaults={
            "user": request.user,
            "ip_address": ip,
            "user_agent": ua,
            "revoked_at": None,
        },
    )
    return row


def touch_session(request) -> None:
    key = getattr(request.session, "session_key", None)
    if not key or not request.user.is_authenticated:
        return
    UserSession.objects.filter(session_key=key, revoked_at__isnull=True).update(
        last_seen_at=timezone.now()
    )


def is_session_revoked(session_key: str) -> bool:
    if not session_key:
        return False
    return UserSession.objects.filter(session_key=session_key, revoked_at__isnull=False).exists()


def list_user_sessions(user, *, current_key: str = ""):
    rows = UserSession.objects.filter(user=user).order_by("-last_seen_at")[:20]
    out = []
    for row in rows:
        out.append(
            {
                "id": row.pk,
                "session_key": row.session_key,
                "label": _ua_label(row.user_agent),
                "ip_address": row.ip_address or "—",
                "created_at": row.created_at,
                "last_seen_at": row.last_seen_at,
                "is_current": row.session_key == current_key,
                "is_active": row.is_active,
            }
        )
    return out


def revoke_session(user, session_key: str, *, current_key: str = "") -> bool:
    if session_key == current_key:
        return False
    row = UserSession.objects.filter(user=user, session_key=session_key, revoked_at__isnull=True).first()
    if not row:
        return False
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at"])
    Session.objects.filter(session_key=session_key).delete()
    return True
