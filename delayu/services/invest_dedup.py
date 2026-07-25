"""Дедупликация проектов (п.3) и валидация реквизитов (п.12)."""
from __future__ import annotations

import re

from django.db.models import Q

from delayu.models_invest import InvestProject


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def inn_is_valid(inn: str) -> bool:
    """Упрощённая проверка ИНН 10/12 (контрольные суммы)."""
    inn = re.sub(r"\D", "", inn or "")
    if len(inn) not in (10, 12):
        return False
    digits = [int(c) for c in inn]

    def checksum(nums, coeffs):
        return sum(n * c for n, c in zip(nums, coeffs)) % 11 % 10

    if len(digits) == 10:
        return checksum(digits[:9], [2, 4, 10, 3, 5, 9, 4, 6, 8]) == digits[9]
    n11 = checksum(digits[:10], [7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
    n12 = checksum(digits[:11], [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8])
    return n11 == digits[10] and n12 == digits[11]


def find_duplicate_project(*, subsystem, name: str = "", investor_inn: str = "", bitrix_id: str = ""):
    if bitrix_id:
        hit = InvestProject.objects.filter(
            subsystem=subsystem, external_ids__bitrix_id=str(bitrix_id)
        ).first()
        if hit:
            return hit, "bitrix_id"
    qs = InvestProject.objects.filter(subsystem=subsystem)
    if investor_inn:
        hit = qs.filter(external_ids__investor_inn=str(investor_inn)).first()
        if hit:
            return hit, "investor_inn"
    if name:
        norm = normalize_name(name)
        for project in qs.only("id", "name", "external_ids")[:500]:
            if normalize_name(project.name) == norm:
                return project, "name"
    return None, ""


def validate_project_requisites(payload: dict) -> list[str]:
    errors = []
    inn = str(payload.get("investor_inn") or payload.get("UF_INN") or "")
    if inn and not inn_is_valid(inn):
        errors.append("invalid_inn")
    email = str(payload.get("contact_email") or payload.get("UF_EMAIL") or "")
    if email and "@" not in email:
        errors.append("invalid_email")
    phone = str(payload.get("contact_phone") or payload.get("UF_PHONE") or "")
    if phone and len(re.sub(r"\D", "", phone)) < 10:
        errors.append("invalid_phone")
    return errors
