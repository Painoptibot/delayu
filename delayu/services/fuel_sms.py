"""SMS для портала «Топливный пропуск» — OTP и пропуск (UI-4)."""
from __future__ import annotations

import hashlib
import logging
import random
import secrets

from django.conf import settings
from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_fuel import FuelCitizen, FuelPermit
from delayu.services.fuel import format_phone_display, normalize_phone

logger = logging.getLogger(__name__)

OTP_SESSION_KEY = "fuel_login_otp"
OTP_TTL_MINUTES = 5


def _demo_mode() -> bool:
    return bool(getattr(settings, "FUEL_SMS_DEMO_MODE", True))


def _otp_storage_key(subsystem_id: int) -> str:
    return f"{OTP_SESSION_KEY}_{subsystem_id}"


def _hash_code(code: str) -> str:
    pepper = getattr(settings, "SECRET_KEY", "dev")
    return hashlib.sha256(f"{code}:{pepper}".encode()).hexdigest()


def log_fuel_sms(subsystem: Subsystem, phone: str, body: str, *, event_code: str) -> None:
    from delayu.models import MailDeliveryLog

    MailDeliveryLog.objects.create(
        subsystem=subsystem,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient=phone[:255],
        subject=event_code[:500],
        event_code=event_code,
        success=True,
        error_message=body[:2000],
    )
    logger.info("fuel_sms %s -> %s: %s", event_code, phone, body[:120])


def dispatch_sms(subsystem: Subsystem, phone: str, body: str, *, event_code: str) -> bool:
    """Отправка SMS: в демо — только журнал; в проде — подключить шлюз."""
    phone_n = normalize_phone(phone)
    if not phone_n:
        return False
    if _demo_mode():
        log_fuel_sms(subsystem, phone_n, body, event_code=event_code)
        return True
    # Точка расширения для SMS-шлюза (SMSC, MTS, etc.)
    log_fuel_sms(subsystem, phone_n, body, event_code=f"{event_code}_queued")
    return True


def start_login_otp(
    request,
    subsystem: Subsystem,
    phone: str,
    full_name: str,
    *,
    channel: str = "sms",
    max_chat_id: str = "",
) -> str | None:
    """
    Сгенерировать OTP и сохранить в сессии.
    В демо-режиме возвращает код для отображения на экране.
    """
    from delayu.services.fuel_notify import dispatch_login_code

    code = f"{random.randint(0, 999999):06d}"
    request.session[_otp_storage_key(subsystem.pk)] = {
        "phone": normalize_phone(phone),
        "full_name": full_name.strip(),
        "code_hash": _hash_code(code),
        "expires": (timezone.now() + timezone.timedelta(minutes=OTP_TTL_MINUTES)).isoformat(),
        "channel": channel,
        "max_chat_id": max_chat_id.strip(),
        "pd_consent": True,
    }
    dispatch_login_code(
        subsystem,
        phone=phone,
        code=code,
        channel=channel,
        max_chat_id=max_chat_id,
    )
    return code if _demo_mode() else None


def verify_login_otp(request, subsystem: Subsystem, code: str) -> tuple[str, str, str, bool] | None:
    """Проверить OTP. Возвращает (phone, full_name, max_chat_id, pd_consent) или None."""
    payload = request.session.get(_otp_storage_key(subsystem.pk))
    if not payload:
        return None
    try:
        expires = timezone.datetime.fromisoformat(payload["expires"])
        if timezone.is_naive(expires):
            expires = timezone.make_aware(expires)
    except (ValueError, TypeError):
        return None
    if timezone.now() > expires:
        request.session.pop(_otp_storage_key(subsystem.pk), None)
        return None
    if _hash_code(code.strip()) != payload.get("code_hash"):
        return None
    request.session.pop(_otp_storage_key(subsystem.pk), None)
    return (
        payload.get("phone", ""),
        payload.get("full_name", ""),
        payload.get("max_chat_id", ""),
        bool(payload.get("pd_consent")),
    )


def clear_login_otp(request, subsystem: Subsystem) -> None:
    request.session.pop(_otp_storage_key(subsystem.pk), None)


def notify_permit_approved(permit: FuelPermit) -> bool:
    """SMS-пропуск после одобрения заявки."""
    app = permit.application
    citizen = app.citizen
    if not citizen.notify_sms:
        return False
    azs_name = permit.assigned_azs.name if permit.assigned_azs else "ближайшая АЗС"
    body = (
        f"Пропуск {permit.number} · ГРЗ {permit.plate} · "
        f"{permit.remaining_liters} л до {permit.valid_until.strftime('%d.%m %H:%M')}. "
        f"Код: {permit.manual_code}. АЗС: {azs_name}"
    )
    return dispatch_sms(permit.subsystem, citizen.phone, body, event_code="fuel_permit_sms")


def link_citizen_esia(
    subsystem: Subsystem,
    *,
    esia_oid: str,
    phone: str = "",
    full_name: str = "",
) -> FuelCitizen:
    phone_n = normalize_phone(phone) if phone else ""
    citizen = None
    if esia_oid:
        citizen = FuelCitizen.objects.filter(
            subsystem=subsystem, esia_oid=esia_oid
        ).first()
    if not citizen and phone_n:
        citizen = FuelCitizen.objects.filter(
            subsystem=subsystem, phone=phone_n
        ).first()
    if citizen:
        updated = []
        if esia_oid and citizen.esia_oid != esia_oid:
            citizen.esia_oid = esia_oid
            updated.append("esia_oid")
        if full_name.strip() and citizen.full_name != full_name.strip():
            citizen.full_name = full_name.strip()
            updated.append("full_name")
        if updated:
            updated.append("updated_at")
            citizen.save(update_fields=updated)
        return citizen
    if not phone_n:
        phone_n = f"esia_{secrets.token_hex(4)}"
    return FuelCitizen.objects.create(
        subsystem=subsystem,
        phone=phone_n,
        full_name=full_name.strip() or f"Гражданин {format_phone_display(phone_n)}",
        esia_oid=esia_oid or "",
    )
