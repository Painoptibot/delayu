"""Одна лента заказчика по всем каналам."""
from __future__ import annotations

from django.utils import timezone

from delayu.services.service_channels import channel_title, ensure_channels


class ServiceFlowError(Exception):
    pass


def post_message(
    *,
    customer,
    channel: str,
    direction: str,
    author_kind: str,
    body: str,
    kind: str = "dialogue",
    scheduled_for=None,
    user=None,
):
    from delayu.models_service import ServiceChannel, ServiceMessage

    text = (body or "").strip()
    if not text:
        raise ServiceFlowError("Пустое сообщение в карточку не пишется.")
    ensure_channels(customer.subsystem)
    account = ServiceChannel.objects.filter(subsystem=customer.subsystem, code=channel).first()
    if account is None:
        raise ServiceFlowError("Такого канала в контуре нет.")
    if direction == ServiceMessage.Direction.OUT and account.status == ServiceChannel.Status.PAUSED:
        raise ServiceFlowError(f"Канал «{account.title}» на паузе. Сообщение не записано.")
    now = timezone.now()
    waiting = bool(scheduled_for and scheduled_for > now)
    return ServiceMessage.objects.create(
        customer=customer,
        subsystem=customer.subsystem,
        channel=channel,
        direction=direction,
        author_kind=author_kind,
        kind=kind,
        body=text,
        status=ServiceMessage.Status.SCHEDULED if waiting else ServiceMessage.Status.SENT,
        scheduled_for=scheduled_for,
        sent_at=None if waiting else now,
        created_by=user,
    )


def release_due(subsystem, now=None) -> int:
    """Подошедшие по сроку сообщения дописывает в карточку актуальным текстом этапа или оплаты."""
    from delayu.models_service import ServiceChannel, ServiceMessage
    from delayu.services.service_agent import compose_payment, compose_stage

    moment = now or timezone.now()
    sent = 0
    due = ServiceMessage.objects.filter(
        subsystem=subsystem,
        status=ServiceMessage.Status.SCHEDULED,
        scheduled_for__lte=moment,
    ).select_related("customer")
    for message in due:
        account = ServiceChannel.objects.filter(
            subsystem=subsystem, code=message.channel
        ).first()
        if account and account.status == ServiceChannel.Status.PAUSED:
            message.last_error = f"Канал «{channel_title(message.channel)}» на паузе."
            message.save(update_fields=["last_error"])
            continue
        if message.kind == ServiceMessage.Kind.STAGE:
            message.body = compose_stage(message.customer)
        elif message.kind == ServiceMessage.Kind.PAYMENT:
            message.body = compose_payment(message.customer)
        message.status = ServiceMessage.Status.SENT
        message.sent_at = moment
        message.last_error = ""
        message.save(update_fields=["body", "status", "sent_at", "last_error"])
        sent += 1
    return sent
