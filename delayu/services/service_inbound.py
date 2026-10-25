"""Входящие SMS, звонок и WhatsApp находят карточку по номеру или открывают New Lead."""
from __future__ import annotations

from delayu.models_service import ServiceCustomer, ServiceMessage
from delayu.services.service_deals import create_deal
from delayu.services.service_dialogue import post_message

LIVE_CHANNELS = ("sms", "phone", "whatsapp")


def address_key(value: str) -> str:
    text = (value or "").strip()
    if "@" in text:
        return text.lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def find_customer(subsystem, address: str):
    key = address_key(address)
    if not key:
        return None
    for customer in ServiceCustomer.objects.filter(subsystem=subsystem):
        if address_key(customer.phone) == key or address_key(customer.email) == key:
            return customer
    return None


def receive_inbound(*, subsystem, channel: str, address: str, body: str, user=None):
    """Пишет входящее в карточку. Незнакомый номер открывает заказчика и сделку New Lead."""
    if channel not in LIVE_CHANNELS:
        from delayu.services.service_dialogue import ServiceFlowError

        raise ServiceFlowError("В карточку сами попадают SMS, звонок и WhatsApp.")
    customer = find_customer(subsystem, address)
    created = False
    if customer is None:
        from delayu.services.service_intake import _next_customer_number

        email = address.strip() if "@" in address else ""
        phone = "" if email else address.strip()
        customer = ServiceCustomer.objects.create(
            subsystem=subsystem,
            number=_next_customer_number(subsystem),
            display_name=address.strip() or "Новый контакт",
            phone=phone,
            email=email,
            stage=ServiceCustomer.Stage.NEW_LEAD,
            tags=channel,
        )
        create_deal(
            customer=customer,
            title=customer.display_name,
            stage=ServiceCustomer.Stage.NEW_LEAD,
            source=channel,
        )
        created = True
    message = post_message(
        customer=customer,
        channel=channel,
        direction=ServiceMessage.Direction.IN,
        author_kind=ServiceMessage.AuthorKind.CUSTOMER,
        body=body,
        user=user,
    )
    return customer, message, created
