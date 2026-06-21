"""#15 — повторная аутентификация перед критичными операциями."""
from __future__ import annotations

import time

from django.contrib.auth import authenticate

from delayu.services.security_policy import profile_for
from delayu.services.totp import profile_totp_enabled, verify_code

REAUTH_TTL_SEC = 300


def is_reauth_valid(request) -> bool:
    ts = request.session.get("reauth_at")
    if not ts:
        return False
    return (time.time() - float(ts)) < REAUTH_TTL_SEC


def mark_reauth(request) -> None:
    session = getattr(request, "session", request)
    session["reauth_at"] = time.time()


def clear_reauth(request) -> None:
    request.session.pop("reauth_at", None)


def verify_reauth(user, password: str, *, totp_code: str = "") -> tuple[bool, str]:
    if not password:
        return False, "Введите пароль"
    auth_user = authenticate(username=user.get_username(), password=password)
    if auth_user is None:
        return False, "Неверный пароль"
    profile = profile_for(user)
    if profile_totp_enabled(profile):
        if not totp_code:
            return False, "Требуется код 2FA"
        if not verify_code(profile.totp_secret, totp_code.strip()):
            return False, "Неверный код 2FA"
    return True, ""


def require_reauth_or_redirect(request, *, next_url: str = ""):
    if is_reauth_valid(request):
        return None
    from django.shortcuts import redirect
    from django.urls import reverse

    target = next_url or request.get_full_path()
    return redirect(f"{reverse('reauth-confirm')}?next={target}")
