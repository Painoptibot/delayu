"""Глобальный поиск по сущностям АИС УЖВ (Ctrl+K)."""
from django.db.models import Q

from delayu.models_uzhv import (
    HousingAppeal,
    HousingCitizen,
    HousingContract,
    HousingCourtCase,
    HousingInspection,
    HousingInspectionOrder,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
    MunicipalBuilding,
)
from delayu.services.privacy import mask_value, user_may_view_pii

UZHV_SEARCH_TYPES = (
    ("uzhv_case", HousingQueueCase, "Учётное дело", "uzhv-cases"),
    ("uzhv_citizen", HousingCitizen, "Гражданин", "uzhv-citizens"),
    ("uzhv_appeal", HousingAppeal, "Обращение", "uzhv-appeals"),
    ("uzhv_building", MunicipalBuilding, "МКД", "uzhv-fund"),
    ("uzhv_contract", HousingContract, "Договор", "uzhv-contracts"),
    ("uzhv_inspection", HousingInspection, "Проверка", "uzhv-inspections"),
    ("uzhv_inspection_order", HousingInspectionOrder, "Предписание на проверку", "uzhv-inspection-order-edit"),
    ("uzhv_prescription", HousingPrescription, "Предписание", "uzhv-prescriptions"),
    ("uzhv_interagency", HousingInteragencyRequest, "Межвед. запрос", "uzhv-interagency"),
    ("uzhv_court", HousingCourtCase, "Судебное дело", "uzhv-court-cases"),
)

TYPE_ALIASES: dict[str, str] = {
    "дело": "uzhv_case",
    "case": "uzhv_case",
    "д": "uzhv_case",
    "гражданин": "uzhv_citizen",
    "citizen": "uzhv_citizen",
    "г": "uzhv_citizen",
    "обращение": "uzhv_appeal",
    "appeal": "uzhv_appeal",
    "о": "uzhv_appeal",
    "мкд": "uzhv_building",
    "building": "uzhv_building",
    "предписание": "uzhv_prescription",
    "prescription": "uzhv_prescription",
    "договор": "uzhv_contract",
    "contract": "uzhv_contract",
    "проверка": "uzhv_inspection",
    "inspection": "uzhv_inspection",
    "предписание на проверку": "uzhv_inspection_order",
    "пв": "uzhv_inspection_order",
    "conduct_order": "uzhv_inspection_order",
    "межвед": "uzhv_interagency",
    "суд": "uzhv_court",
    "court": "uzhv_court",
}


def parse_uzhv_search_query(raw: str) -> tuple[str | None, str]:
    q = (raw or "").strip()
    if ":" in q:
        prefix, rest = q.split(":", 1)
        prefix = prefix.strip().lower()
        rest = rest.strip()
        if prefix in TYPE_ALIASES:
            return TYPE_ALIASES[prefix], rest
    return None, q


def _display_name(full_name: str, *, allow_pii: bool) -> str:
    if allow_pii or not full_name:
        return full_name
    return mask_value(full_name, 1)


def _filter_qs(kind: str, qs, q: str):
    if kind == "uzhv_case":
        return qs.filter(
            Q(case_number__icontains=q)
            | Q(citizen__last_name__icontains=q)
            | Q(citizen__first_name__icontains=q)
            | Q(citizen__snils__icontains=q)
        ).select_related("citizen")
    if kind == "uzhv_citizen":
        return qs.filter(
            Q(last_name__icontains=q)
            | Q(first_name__icontains=q)
            | Q(middle_name__icontains=q)
            | Q(snils__icontains=q)
            | Q(reg_address__icontains=q)
        )
    if kind == "uzhv_appeal":
        return qs.filter(
            Q(appeal_number__icontains=q)
            | Q(subject__icontains=q)
            | Q(citizen__last_name__icontains=q)
        ).select_related("citizen")
    if kind == "uzhv_building":
        return qs.filter(Q(address__icontains=q) | Q(cadastral_number__icontains=q))
    if kind == "uzhv_contract":
        return qs.filter(
            Q(contract_number__icontains=q) | Q(citizen__last_name__icontains=q)
        ).select_related("citizen")
    if kind == "uzhv_inspection":
        return qs.filter(
            Q(inspection_number__icontains=q)
            | Q(check_subject__icontains=q)
            | Q(counterparty_name__icontains=q)
            | Q(building__address__icontains=q)
        ).select_related("building")
    if kind == "uzhv_inspection_order":
        return qs.filter(
            Q(order_number__icontains=q)
            | Q(addressee__icontains=q)
            | Q(check_subject__icontains=q)
            | Q(building__address__icontains=q)
        ).select_related("building")
    if kind == "uzhv_prescription":
        return qs.filter(
            Q(prescription_number__icontains=q)
            | Q(description__icontains=q)
            | Q(inspection__inspection_number__icontains=q)
        ).select_related("inspection")
    if kind == "uzhv_interagency":
        return qs.filter(
            Q(request_number__icontains=q)
            | Q(subject__icontains=q)
            | Q(recipient_name__icontains=q)
        )
    if kind == "uzhv_court":
        return qs.filter(
            Q(case_number__icontains=q)
            | Q(court_name__icontains=q)
            | Q(defendant_name__icontains=q)
        )
    return qs.none()


def _title(kind: str, obj, *, allow_pii: bool) -> str:
    if kind == "uzhv_case":
        name = _display_name(obj.citizen.full_name, allow_pii=allow_pii)
        return f"{obj.case_number} — {name}"
    if kind == "uzhv_citizen":
        return _display_name(obj.full_name, allow_pii=allow_pii)
    if kind == "uzhv_appeal":
        return f"{obj.appeal_number} — {obj.subject[:80]}"
    if kind == "uzhv_building":
        return obj.address
    if kind == "uzhv_contract":
        name = _display_name(obj.citizen.full_name, allow_pii=allow_pii)
        return f"{obj.contract_number} — {name}"
    if kind == "uzhv_inspection":
        addr = obj.building.address if obj.building_id else obj.counterparty_name
        return f"{obj.inspection_number} — {addr[:60]}"
    if kind == "uzhv_inspection_order":
        addr = obj.building.address if obj.building_id else obj.check_address or obj.addressee
        return f"{obj.order_number} — {addr[:60]}"
    if kind == "uzhv_prescription":
        return f"{obj.prescription_number} — {obj.description[:60]}"
    if kind == "uzhv_interagency":
        return f"{obj.request_number} — {obj.subject[:60]}"
    if kind == "uzhv_court":
        return f"{obj.case_number} — {obj.court_name[:50]}"
    return str(obj)


def uzhv_global_search(subsystem, query: str, *, limit: int = 20, user=None):
    type_filter, q = parse_uzhv_search_query(query)
    if len(q) < 2 and not type_filter:
        return []
    if len(q) < 2:
        return []
    allow_pii = user_may_view_pii(user) if user else False
    types = UZHV_SEARCH_TYPES
    if type_filter:
        types = [t for t in UZHV_SEARCH_TYPES if t[0] == type_filter]
        if not types:
            return []
    per_type = max(2, limit // max(len(types), 1))
    results = []
    for kind, model, label, url_name in types:
        if kind == "uzhv_prescription":
            qs = model.objects.filter(inspection__subsystem=subsystem)
        elif kind == "uzhv_inspection_order":
            qs = model.objects.filter(subsystem=subsystem)
        else:
            qs = model.objects.filter(subsystem=subsystem)
        qs = _filter_qs(kind, qs, q)
        for obj in qs[:per_type]:
            results.append(
                {
                    "type": kind,
                    "type_label": label,
                    "id": obj.pk,
                    "title": _title(kind, obj, allow_pii=allow_pii),
                    "url_name": url_name,
                    "open_on_list": kind not in ("uzhv_inspection_order",),
                }
            )
        if len(results) >= limit:
            break
    return results[:limit]
