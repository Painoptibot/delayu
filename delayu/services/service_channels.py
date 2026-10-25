"""Каналы одной карточки: соцсети, телефония, SMS и почта."""
from __future__ import annotations

# Каналы разговора в американском HighLevel. MAX, Viber и Telegram сюда не входят.
CHANNEL_SPECS = (
    ("sms", "SMS", "Text message to the customer phone"),
    ("phone", "Phone", "Call and the call note on the same card"),
    ("email", "Email", "Email to the customer"),
    ("facebook", "Facebook", "Facebook Messenger"),
    ("instagram", "Instagram", "Instagram messages"),
    ("whatsapp", "WhatsApp", "WhatsApp thread"),
    ("tiktok", "TikTok", "TikTok messages"),
    ("google", "Google Business", "Google Business messages"),
    ("webchat", "Live chat", "Website chat widget"),
)

CHANNEL_CODES = {code for code, _title, _detail in CHANNEL_SPECS}
LEGACY_CODES = {"max", "viber", "telegram"}


def ensure_channels(subsystem):
    from delayu.models_service import ServiceChannel

    for code, title, detail in CHANNEL_SPECS:
        ServiceChannel.objects.get_or_create(
            subsystem=subsystem,
            code=code,
            defaults={"title": title, "detail": detail},
        )
    ServiceChannel.objects.filter(subsystem=subsystem, code__in=LEGACY_CODES).delete()
    return ServiceChannel.objects.filter(subsystem=subsystem)


def channel_title(code: str) -> str:
    for item_code, title, _detail in CHANNEL_SPECS:
        if item_code == code:
            return title
    return code
