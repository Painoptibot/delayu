"""Сохранение договоров УЖВ и статуса помещений."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from delayu.models_uzhv import HousingContract, MunicipalPremise


def sync_premise_occupancy(premise: MunicipalPremise | None) -> None:
    if not premise:
        return
    has_active = premise.contracts.filter(is_active=True).exists()
    new_status = MunicipalPremise.Status.OCCUPIED if has_active else MunicipalPremise.Status.FREE
    if premise.status != new_status:
        premise.status = new_status
        premise.save(update_fields=["status"])


@transaction.atomic
def save_housing_contract(contract: HousingContract, *, old_premise_id: int | None = None) -> HousingContract:
    if not contract.is_active and not contract.terminated_at:
        contract.terminated_at = timezone.now().date()
    if contract.is_active:
        contract.terminated_at = None
        contract.termination_reason = ""
    contract.save()
    sync_premise_occupancy(contract.premise)
    if old_premise_id and old_premise_id != (contract.premise_id or 0):
        old = MunicipalPremise.objects.filter(pk=old_premise_id).first()
        if old:
            sync_premise_occupancy(old)
    return contract
