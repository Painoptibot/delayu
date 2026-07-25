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


def dedupe_pair_key(left: InvestProject, right: InvestProject) -> str:
    first, second = sorted([left.pk, right.pk])
    return f"{first}:{second}"


def ignored_dedupe_keys(project: InvestProject) -> set[str]:
    return set((project.external_ids or {}).get("dedupe_ignored", []))


def is_dedupe_ignored(left: InvestProject, right: InvestProject) -> bool:
    key = dedupe_pair_key(left, right)
    return key in ignored_dedupe_keys(left) or key in ignored_dedupe_keys(right)


def ignore_duplicate_pair(left: InvestProject, right: InvestProject) -> str:
    key = dedupe_pair_key(left, right)
    for project in (left, right):
        external_ids = dict(project.external_ids or {})
        ignored = list(dict.fromkeys([*external_ids.get("dedupe_ignored", []), key]))
        external_ids["dedupe_ignored"] = ignored
        project.external_ids = external_ids
        project.save(update_fields=["external_ids", "updated_at"])
    return key


def suspected_duplicate_pairs(subsystem) -> list[dict]:
    projects = list(
        InvestProject.objects.filter(subsystem=subsystem)
        .select_related("organization", "investor_entity")
        .order_by("id")
    )
    pairs = []
    seen = set()
    for project in projects:
        match, reason = find_duplicate_project(
            subsystem=subsystem,
            name=project.name,
            investor_inn=(project.investor_entity.inn if project.investor_entity else project.external_ids.get("investor_inn", "")),
            bitrix_id=project.external_ids.get("bitrix_id", ""),
        )
        if not match or match.pk == project.pk:
            for candidate in projects:
                if candidate.pk == project.pk:
                    continue
                if normalize_name(candidate.name) == normalize_name(project.name):
                    match, reason = candidate, "name"
                    break
        if not match or match.pk == project.pk:
            continue
        key = dedupe_pair_key(project, match)
        if key in seen or is_dedupe_ignored(project, match):
            continue
        seen.add(key)
        reason_label = {
            "bitrix_id": "Совпадает Bitrix ID",
            "investor_inn": "Совпадает ИНН инвестора",
            "name": "Совпадает наименование",
        }.get(reason, reason or "Возможный дубль")
        pairs.append({"key": key, "left": project, "right": match, "reason": reason, "reason_label": reason_label})
    return pairs


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
