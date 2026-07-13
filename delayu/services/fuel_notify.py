"""Уведомления жителям: SMS и MAX."""
from __future__ import annotations

from delayu.models import Subsystem
from delayu.models_fuel import FuelCitizen, FuelPermit
from delayu.services.fuel_sms import dispatch_sms
from delayu.services.max_messenger import get_max_channel, send_max_message


def max_available(subsystem: Subsystem) -> bool:
    return bool(get_max_channel(subsystem))


def dispatch_login_code(
    subsystem: Subsystem,
    *,
    phone: str,
    code: str,
    channel: str,
    max_chat_id: str = "",
) -> None:
    body = f"Код входа «Топливный пропуск»: {code}. Действует 5 мин."
    if channel in ("sms", "both"):
        dispatch_sms(subsystem, phone, body, event_code="fuel_otp")
    if channel in ("max", "both") and max_chat_id.strip():
        send_max_message(
            subsystem,
            max_chat_id.strip(),
            body,
            event_code="fuel_otp_max",
        )


def notify_permit_approved_channels(permit: FuelPermit) -> None:
    """Дублирование пропуска по SMS и/или MAX."""
    from delayu.services.fuel_sms import notify_permit_approved

    citizen = permit.application.citizen
    if citizen.notify_sms:
        notify_permit_approved(permit)
    if citizen.notify_max and citizen.max_chat_id.strip():
        azs_name = permit.assigned_azs.name if permit.assigned_azs else "ближайшая АЗС"
        body = (
            f"Пропуск {permit.number} · ГРЗ {permit.plate} · "
            f"{permit.remaining_liters} л до {permit.valid_until.strftime('%d.%m %H:%M')}. "
            f"Код: {permit.manual_code}. АЗС: {azs_name}"
        )
        send_max_message(
            permit.subsystem,
            citizen.max_chat_id.strip(),
            body,
            event_code="fuel_permit_max",
        )


def log_support_question(
    subsystem: Subsystem,
    *,
    citizen: FuelCitizen | None,
    name: str,
    contact: str,
    question: str,
) -> "FuelSupportTicket":
    from delayu.models import MailDeliveryLog
    from delayu.models_fuel import FuelEventLog, FuelSupportTicket
    from delayu.services.fuel_events import log_fuel_event

    who = citizen.full_name if citizen else name
    ticket = FuelSupportTicket.objects.create(
        subsystem=subsystem,
        citizen=citizen,
        name=name.strip(),
        contact=contact.strip(),
        question=question.strip(),
    )
    MailDeliveryLog.objects.create(
        subsystem=subsystem,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient=(contact or who)[:255],
        subject="fuel_support_question",
        event_code="fuel_support_question",
        success=True,
        error_message=question[:2000],
    )
    log_fuel_event(
        subsystem,
        FuelEventLog.Channel.CITIZEN,
        "citizen.support",
        f"Обращение в ТП · {name.strip()}",
        citizen=citizen,
        object_type="FuelSupportTicket",
        object_id=ticket.pk,
        payload={"contact": contact.strip()[:64]},
    )
    if citizen and citizen.max_chat_id.strip() and max_available(subsystem):
        send_max_message(
            subsystem,
            citizen.max_chat_id.strip(),
            f"Ваш вопрос принят: {question[:500]}",
            event_code="fuel_support_ack",
        )
    return ticket
