"""Server-side Web Push для АИС УЖВ."""
from __future__ import annotations

import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _subscription_for_user(user) -> dict | None:
    profile = getattr(user, "delayu_profile", None)
    if not profile:
        return None
    sub = getattr(profile, "uzhv_push_subscription", None) or {}
    if not (sub.get("endpoint") or "").strip():
        return None
    return sub


def send_uzhv_web_push(user, *, title: str, body: str, url: str = "") -> bool:
    """Отправляет Web Push при наличии VAPID-ключей и subscription в профиле."""
    private_key = (getattr(settings, "UZHV_VAPID_PRIVATE_KEY", "") or "").strip()
    if not private_key:
        return False
    sub = _subscription_for_user(user)
    if not sub:
        return False
    try:
        from pywebpush import WebPushException, webpush
    except ImportError:
        logger.debug("pywebpush not installed")
        return False

    payload = json.dumps(
        {"title": title[:120], "body": body[:500], "url": url or "/uzhv/"},
        ensure_ascii=False,
    )
    try:
        webpush(
            subscription_info=sub,
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={"sub": "mailto:noreply@delayu.local"},
        )
        return True
    except WebPushException as exc:
        logger.warning("Web Push failed for user %s: %s", user.pk, exc)
        return False
