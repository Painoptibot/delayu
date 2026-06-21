"""Обработка входящих сообщений интеграций (webhook → дела/обращения)."""
from __future__ import annotations

import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.utils import timezone

from delayu.models import IntegrationEndpoint
from delayu.models_uzhv import HousingCitizen
from delayu.services.integrations import receive_inbound
from delayu.services.uzhv import register_housing_appeal

logger = logging.getLogger(__name__)
User = get_user_model()


def integration_actor(subsystem):
    """Системный пользователь для автоматических операций."""
    from delayu.models import SubsystemMembership

    mem = (
        SubsystemMembership.objects.filter(subsystem=subsystem)
        .select_related("user", "role")
        .order_by("pk")
        .first()
    )
    if mem:
        return mem.user
    return User.objects.filter(is_superuser=True).order_by("pk").first()


def verify_inbound_access(request, endpoint: IntegrationEndpoint) -> str | None:
    """
    Проверка доступа: X-Integration-Secret и/или API-ключ подсистемы.
    Возвращает текст ошибки или None при успехе.
    """
    if not endpoint.config.get("allow_inbound"):
        return "inbound_disabled"

    from delayu.services.api_gateway import extract_api_key, verify_api_key

    secret = (endpoint.config.get("inbound_secret") or "").strip()
    headers = getattr(request, "headers", None) or {}
    header = (headers.get("X-Integration-Secret") or "").strip()
    raw_key = extract_api_key(request) if hasattr(request, "GET") else ""
    api_ok = False
    if raw_key:
        key = verify_api_key(raw_key)
        api_ok = bool(key and key.subsystem_id == endpoint.subsystem_id)

    if secret:
        if header == secret or api_ok:
            return None
        return "invalid_secret"
    if api_ok:
        return None
    return "auth_required"


def process_inbound(endpoint: IntegrationEndpoint, payload: dict) -> dict:
    """Запись в журнал + обработчик по inbound_handler в config."""
    msg = receive_inbound(endpoint, payload)
    handler = (endpoint.config.get("inbound_handler") or "").strip()
    result: dict = {
        "ok": True,
        "message_id": msg.pk,
        "handler": handler or None,
    }

    if handler in ("uzhv.epgu.appeal", "uzhv.mfc.application"):
        result.update(handle_epgu_appeal(endpoint.subsystem, payload, source=handler))
    elif handler == "telegram.update":
        result.update(handle_telegram_update(endpoint.subsystem, payload))
    elif handler == "external.1c.case":
        result.update(handle_1c_case(endpoint.subsystem, payload))
    else:
        result["note"] = "stored_only"

    return result


def handle_epgu_appeal(subsystem, payload: dict, *, source: str = "uzhv.epgu.appeal") -> dict:
    """
    Регистрация обращения из внешнего канала (ЕПГУ / МФЦ / портал).
    payload: subject, body?, citizen{last_name, first_name, middle_name, snils, phone, email},
              external_id?, received_at? (YYYY-MM-DD)
    """
    actor = integration_actor(subsystem)
    if not actor:
        return {"ok": False, "error": "no_actor"}

    citizen_data = payload.get("citizen") or {}
    citizen = _find_or_create_citizen(subsystem, citizen_data)
    subject = (payload.get("subject") or "Обращение с внешнего портала")[:500]
    body = (payload.get("body") or "")[:5000]
    received_at = _parse_date(payload.get("received_at")) or timezone.now().date()

    ext = (payload.get("external_id") or "").strip()
    channel = "МФЦ" if "mfc" in source else "ЕПГУ"
    if ext:
        body = f"[{channel}, внешний ID: {ext}]\n{body}".strip()
    elif source == "uzhv.mfc.application":
        body = f"[Канал: МФЦ]\n{body}".strip()

    appeal = register_housing_appeal(
        subsystem=subsystem,
        user=actor,
        subject=subject,
        body=body,
        citizen=citizen,
        assignee=payload.get("assignee_id") and User.objects.filter(pk=payload["assignee_id"]).first(),
        received_at=received_at,
    )

    return {
        "appeal_id": appeal.pk,
        "appeal_number": appeal.appeal_number,
        "citizen_id": citizen.pk,
    }


def _find_or_create_citizen(subsystem, data: dict) -> HousingCitizen:
    snils = (data.get("snils") or "").strip()
    if snils:
        existing = HousingCitizen.objects.filter(subsystem=subsystem, snils=snils).first()
        if existing:
            return existing
    return HousingCitizen.objects.create(
        subsystem=subsystem,
        last_name=(data.get("last_name") or "—")[:128],
        first_name=(data.get("first_name") or "")[:128],
        middle_name=(data.get("middle_name") or "")[:128],
        snils=snils[:14],
        phone=(data.get("phone") or "")[:32],
        email=(data.get("email") or "")[:254],
    )


def _parse_date(value) -> datetime.date | None:
    if not value:
        return None
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def handle_1c_case(subsystem, payload: dict) -> dict:
    """
    Импорт/обновление учётного дела из 1С (JSON).
    payload: case_number?, external_id?, status?, citizen{...}, notes?
    """
    from delayu.models_uzhv import HousingCitizen, HousingQueueCase
    from delayu.services.uzhv import next_case_number
    from delayu.services.uzhv_case_status import record_case_status_change

    actor = integration_actor(subsystem)
    citizen_data = payload.get("citizen") or {}
    citizen = None
    if citizen_data:
        citizen = _find_or_create_citizen(subsystem, citizen_data)

    case_number = (payload.get("case_number") or "").strip()
    external_id = (payload.get("external_id") or "").strip()
    case = None
    if case_number:
        case = HousingQueueCase.objects.filter(subsystem=subsystem, case_number=case_number).first()
    if not case and external_id:
        case = HousingQueueCase.objects.filter(
            subsystem=subsystem, notes__icontains=external_id
        ).first()

    if case:
        old = case.status
        if payload.get("status"):
            case.status = payload["status"]
        if citizen:
            case.citizen = citizen
        if external_id and external_id not in (case.notes or ""):
            case.notes = f"1С: {external_id}\n{case.notes or ''}".strip()
        case.save()
        if payload.get("status") and old != case.status:
            record_case_status_change(
                case, old_status=old, new_status=case.status, user=actor, comment="Синхронизация 1С"
            )
        return {"case_id": case.pk, "case_number": case.case_number, "action": "updated"}

    if not citizen:
        citizen = _find_or_create_citizen(
            subsystem, {"last_name": "Импорт", "first_name": "1С", "external_id": external_id}
        )
    case = HousingQueueCase.objects.create(
        subsystem=subsystem,
        case_number=case_number or next_case_number(subsystem),
        citizen=citizen,
        status=payload.get("status") or HousingQueueCase.Status.REGISTERED,
        notes=f"1С: {external_id}" if external_id else "",
    )
    record_case_status_change(
        case,
        old_status="",
        new_status=case.status,
        user=actor,
        comment="Импорт из 1С",
    )
    return {"case_id": case.pk, "case_number": case.case_number, "action": "created"}


def handle_telegram_update(subsystem, payload: dict) -> dict:
    """Обработка Update от Telegram Bot API."""
    message = payload.get("message") or payload.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = (message.get("text") or "").strip()
    if not chat_id:
        return {"ok": False, "error": "no_chat"}

    reply = _telegram_command_reply(text)
    sent = False
    if reply:
        from delayu.services.telegram import send_telegram_message

        sent = send_telegram_message(
            subsystem,
            str(chat_id),
            reply,
            event_code="telegram_inbound",
        )

    return {"chat_id": chat_id, "text": text[:200], "replied": sent}


def _telegram_command_reply(text: str) -> str:
    cmd = (text.split()[0] if text else "").lower()
    if cmd in ("/start", "/help"):
        return (
            "АИС УЖВ — бот уведомлений.\n"
            "Команды: /help, /status\n"
            "Привяжите chat_id в профиле пользователя для push."
        )
    if cmd == "/status":
        return "Откройте кабинет УЖВ в браузере для актуальных сроков и обращений."
    if text:
        return ""
    return ""


def verify_telegram_webhook(request, subsystem) -> str | None:
    from django.conf import settings

    expected = (getattr(settings, "TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
    if not expected:
        channel_secret = ""
        from delayu.models import MessengerChannel

        ch = (
            MessengerChannel.objects.filter(
                subsystem=subsystem,
                channel_type=MessengerChannel.ChannelType.TELEGRAM,
                is_active=True,
            )
            .first()
        )
        if ch and ch.notes:
            for line in ch.notes.splitlines():
                if line.strip().lower().startswith("webhook_secret:"):
                    channel_secret = line.split(":", 1)[1].strip()
        expected = channel_secret
    if not expected:
        return None
    token = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
    if token != expected:
        return "invalid_telegram_secret"
    return None
