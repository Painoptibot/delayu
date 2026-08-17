# -*- coding: utf-8 -*-
"""Вход в приложение ЮФО: телефон + код, как на портале жителя."""
from __future__ import annotations

import hashlib
import random
from typing import Any

from django.conf import settings
from django.core.cache import cache

from delayu.services.fuel import format_phone_display, normalize_phone

OTP_TTL = 300
SESSION_KEY = "fuel_ufo_user"


def _demo_mode() -> bool:
    return bool(getattr(settings, "FUEL_SMS_DEMO_MODE", True))


def _hash_code(code: str) -> str:
    pepper = getattr(settings, "SECRET_KEY", "dev")
    return hashlib.sha256(f"ufo:{code}:{pepper}".encode()).hexdigest()


def start_ufo_otp(phone: str, full_name: str) -> dict[str, Any]:
    phone_n = normalize_phone(phone)
    if len(phone_n) < 11:
        raise ValueError("Укажите телефон в формате +7…")
    name = (full_name or "").strip()
    if len(name) < 2:
        raise ValueError("Укажите фамилию и имя")
    code = f"{random.randint(0, 9999):04d}"
    cache.set(
        f"fuel_ufo_otp:{phone_n}",
        {"code_hash": _hash_code(code), "name": name[:120]},
        OTP_TTL,
    )
    out = {
        "ok": True,
        "phone": phone_n,
        "phone_display": format_phone_display(phone_n),
        "ttl_sec": OTP_TTL,
        "channel": "sms",
    }
    if _demo_mode():
        out["demo_code"] = code
    return out


def verify_ufo_otp(request, phone: str, code: str) -> dict[str, Any] | None:
    phone_n = normalize_phone(phone)
    payload = cache.get(f"fuel_ufo_otp:{phone_n}")
    if not payload:
        return None
    if payload.get("code_hash") != _hash_code((code or "").strip()):
        return None
    cache.delete(f"fuel_ufo_otp:{phone_n}")
    user = {
        "phone": phone_n,
        "phone_display": format_phone_display(phone_n),
        "name": payload.get("name") or "",
        "auth_source": "otp",
    }
    request.session[SESSION_KEY] = user
    request.session.modified = True
    return user


def current_ufo_user(request) -> dict[str, Any] | None:
    user = request.session.get(SESSION_KEY)
    return user if isinstance(user, dict) and user.get("phone") else None


def logout_ufo(request) -> None:
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
