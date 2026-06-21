"""PWA / мобильные оповещения АИС УЖВ."""
from __future__ import annotations

from delayu.models import Notification
from delayu.services.uzhv_overdue import list_overdue_items


def uzhv_user_alerts(subsystem, user) -> dict:
    """JSON для PWA: просрочки и непрочитанные уведомления текущего пользователя."""
    if not user or not user.is_authenticated:
        return {
            "overdue_count": 0,
            "unread_notifications": 0,
            "has_alerts": False,
        }
    overdue = len(
        list_overdue_items(subsystem, assignee_id=user.pk, limit=200)
    )
    unread = Notification.objects.filter(
        user=user, subsystem=subsystem, is_read=False
    ).count()
    return {
        "overdue_count": overdue,
        "unread_notifications": unread,
        "has_alerts": overdue > 0 or unread > 0,
        "hub_url": "/uzhv/",
    }


def save_push_subscription(user, payload: dict) -> bool:
    """Сохраняет Web Push subscription в профиле пользователя."""
    if not user or not user.is_authenticated:
        return False
    endpoint = (payload.get("endpoint") or "").strip()
    if not endpoint:
        return False
    from delayu.models_business import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.uzhv_push_subscription = payload
    profile.save(update_fields=["uzhv_push_subscription"])
    return True


def clear_push_subscription(user) -> None:
    if not user or not user.is_authenticated:
        return
    profile = getattr(user, "delayu_profile", None)
    if not profile:
        return
    profile.uzhv_push_subscription = {}
    profile.save(update_fields=["uzhv_push_subscription"])


def push_subscription_status(user) -> dict:
    """Статус Web Push подписки пользователя для UI."""
    from django.conf import settings

    profile = getattr(user, "delayu_profile", None)
    sub = (getattr(profile, "uzhv_push_subscription", None) or {}) if profile else {}
    endpoint = (sub.get("endpoint") or "").strip()
    vapid = bool((getattr(settings, "UZHV_VAPID_PUBLIC_KEY", "") or "").strip())
    return {
        "subscribed": bool(endpoint),
        "endpoint_preview": endpoint[:48] + "…" if len(endpoint) > 48 else endpoint,
        "vapid_configured": vapid,
        "can_subscribe": vapid,
    }


def user_has_uzhv_membership(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    from delayu.models import SubsystemMembership

    return SubsystemMembership.objects.filter(
        user=user, subsystem__industry_template="uzhv"
    ).exists()
