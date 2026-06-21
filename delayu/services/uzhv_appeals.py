"""Регистрация исходящих ответов на обращения (ТЗ п. 354)."""
from __future__ import annotations

from django.db import transaction

from delayu.models import Correspondence, CorrespondenceEvent
from delayu.models_uzhv import HousingAppeal
from delayu.services.correspondence import log_event, register_correspondence


@transaction.atomic
def register_appeal_outgoing(appeal: HousingAppeal, *, user) -> Correspondence:
    """Регистрирует исходящий ответ в M24 и связывает с обращением."""
    if appeal.outgoing_correspondence_id:
        return appeal.outgoing_correspondence
    counterparty = appeal.citizen.full_name if appeal.citizen_id else ""
    subject = f"Ответ на обращение {appeal.appeal_number}: {appeal.subject[:200]}"
    corr = register_correspondence(
        subsystem=appeal.subsystem,
        user=user,
        direction=Correspondence.Direction.OUT,
        subject=subject,
        counterparty=counterparty,
        assignee=appeal.assignee,
        linked_incoming=appeal.correspondence,
        status=Correspondence.Status.REGISTERED,
    )
    appeal.outgoing_correspondence = corr
    appeal.save(update_fields=["outgoing_correspondence", "updated_at"])
    if appeal.correspondence_id:
        log_event(
            appeal.correspondence,
            CorrespondenceEvent.EventType.STATUS,
            f"Зарегистрирован исходящий ответ {corr.reg_number}",
            actor=user,
        )
    return corr
