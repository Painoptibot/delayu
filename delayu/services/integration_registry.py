"""Статус внешних интеграций для UI (шлюз, хаб УЖВ). СМЭВ — отдельно, этап 2."""
from __future__ import annotations

from django.conf import settings

from delayu.models import IntegrationEndpoint, MessengerChannel, NotificationTemplate
from delayu.services.dadata import integration_status as dadata_status


def _item(code, name, enabled, hint, docs_url=""):
    row = {"code": code, "name": name, "enabled": enabled, "hint": hint}
    if docs_url:
        row["docs_url"] = docs_url
    return row


def external_services_for_subsystem(subsystem) -> list[dict]:
    items = [dadata_status()]

    yandex = bool(getattr(settings, "YANDEX_MAPS_API_KEY", "").strip())
    items.append(
        _item("yandex_maps", "Яндекс.Карты", yandex, "Карта МКД и геокодирование", "https://developer.tech.yandex.ru/")
    )

    tg = (
        MessengerChannel.objects.filter(
            subsystem=subsystem,
            channel_type=MessengerChannel.ChannelType.TELEGRAM,
            is_active=True,
        )
        .exclude(webhook_url__icontains="/bot/demo")
        .exists()
        or bool(getattr(settings, "TELEGRAM_BOT_TOKEN", "").strip())
    )
    items.append(_item("telegram", "Telegram", tg, "M41 + TELEGRAM_BOT_TOKEN", "https://core.telegram.org/bots/api"))

    max_ch = MessengerChannel.objects.filter(
        subsystem=subsystem, channel_type=MessengerChannel.ChannelType.MAX, is_active=True
    ).exists()
    items.append(_item("max", "MAX", max_ch, "Канал max_uzhv — журнал / API"))

    webhooks = IntegrationEndpoint.objects.filter(
        subsystem=subsystem,
        is_active=True,
        endpoint_type__in=(
            IntegrationEndpoint.EndpointType.WEBHOOK,
            IntegrationEndpoint.EndpointType.REST,
        ),
    ).count()
    items.append(_item("webhooks", "Исходящие webhook / n8n", webhooks > 0, f"Активных: {webhooks}"))

    inbound = IntegrationEndpoint.objects.filter(
        subsystem=subsystem, is_active=True, config__allow_inbound=True
    ).count()
    items.append(_item("inbound", "Входящие API", inbound > 0, "ЕПГУ, 1С, Telegram journal"))

    items.append(
        _item(
            "public_form",
            "Публичная форма",
            True,
            f"/public/{subsystem.code}/appeal/",
        )
    )

    email_ok = "console" not in settings.EMAIL_BACKEND.lower()
    items.append(_item("email", "E-mail (SMTP)", email_ok, "EMAIL_* + шаблоны M78"))

    push_ok = bool(getattr(settings, "UZHV_VAPID_PUBLIC_KEY", "").strip())
    items.append(_item("webpush", "Web Push", push_ok, "UZHV_VAPID_*"))

    items.append(_item("ical", "iCal / сроки", True, "/uzhv/deadlines/export/?format=ical"))

    tpl_count = NotificationTemplate.objects.filter(
        subsystem=subsystem, event_code__startswith="uzhv_", is_active=True
    ).count()
    items.append(_item("uzhv_notify", "Шаблоны уведомлений", tpl_count >= 3, f"uzhv_*: {tpl_count}"))

    sso_count = 0
    try:
        from delayu.models import SsoProvider

        sso_count = SsoProvider.objects.filter(subsystem=subsystem, is_active=True).count()
    except Exception:
        pass
    items.append(_item("sso", "SSO / OIDC / ЕСИА", sso_count > 0, "/infra/sso/"))

    items.append(
        _item(
            "smev",
            "СМЭВ / ГИС ЖКХ",
            False,
            "Этап 2 (I-xx) — не в бесплатном контуре",
        )
    )

    return items
