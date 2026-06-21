"""Массовые операции в реестрах АИС УЖВ."""
from __future__ import annotations

import csv
import io

from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone

from delayu.models_uzhv import (
    HousingAdminProtocol,
    HousingAppeal,
    HousingCitizen,
    HousingContract,
    HousingCourtCase,
    HousingInspection,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
    OrphanHousingRecord,
    YoungFamilyRecord,
)


def _csv_response(filename: str, rows: list[list]) -> HttpResponse:
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    for row in rows:
        writer.writerow(row)
    content = "\ufeff" + buf.getvalue()
    resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp


def export_cases_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingQueueCase.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("citizen", "assignee")
        .order_by("case_number")
    )
    rows = [
        [
            "Номер",
            "Гражданин",
            "Категория",
            "Статус",
            "На учёте с",
            "Очерёдность",
            "Исполнитель",
        ]
    ]
    for c in qs:
        assignee = ""
        if c.assignee:
            assignee = c.assignee.get_full_name() or c.assignee.username
        rows.append(
            [
                c.case_number,
                c.citizen.full_name,
                c.get_category_display(),
                c.get_status_display(),
                c.registered_at.strftime("%d.%m.%Y"),
                c.queue_position or "",
                assignee,
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_cases_{stamp}.csv", rows)


def export_appeals_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingAppeal.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("citizen", "assignee", "housing_case")
        .order_by("-received_at")
    )
    rows = [
        [
            "Номер",
            "Тема",
            "Заявитель",
            "Дело",
            "Поступило",
            "Срок ответа",
            "Статус",
            "Исполнитель",
        ]
    ]
    for a in qs:
        rows.append(
            [
                a.appeal_number,
                a.subject,
                a.citizen.full_name if a.citizen_id else "",
                a.housing_case.case_number if a.housing_case_id else "",
                a.received_at.strftime("%d.%m.%Y"),
                a.due_date.strftime("%d.%m.%Y"),
                a.get_status_display(),
                (a.assignee.get_full_name() or a.assignee.username) if a.assignee_id else "",
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_appeals_{stamp}.csv", rows)


def bulk_set_case_status(subsystem, ids: list[int], status: str, *, user=None) -> int:
    if status not in dict(HousingQueueCase.Status.choices):
        return 0
    from delayu.services.uzhv_case_status import record_case_status_change

    cases = list(HousingQueueCase.objects.filter(subsystem=subsystem, pk__in=ids))
    history = []
    for case in cases:
        if case.status == status:
            continue
        entry = record_case_status_change(
            case, old_status=case.status, new_status=status, user=user
        )
        if entry:
            history.append(entry)
    updated = HousingQueueCase.objects.filter(subsystem=subsystem, pk__in=ids).update(
        status=status, updated_at=timezone.now()
    )
    from delayu.services.uzhv_queue import recalculate_housing_queue

    recalculate_housing_queue(subsystem)
    return updated


def bulk_set_appeal_status(subsystem, ids: list[int], status: str, *, user=None) -> int:
    if status not in dict(HousingAppeal.Status.choices):
        return 0
    from delayu.services.uzhv_appeal_status import record_appeal_status_change

    updated = 0
    for appeal in HousingAppeal.objects.filter(subsystem=subsystem, pk__in=ids):
        old = appeal.status
        if old == status:
            continue
        appeal.status = status
        appeal.save(update_fields=["status", "updated_at"])
        record_appeal_status_change(
            appeal, old_status=old, new_status=status, user=user, comment="Массовая операция"
        )
        updated += 1
    return updated


def export_inspections_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingInspection.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("building", "inspector")
        .order_by("-planned_date")
    )
    rows = [
        [
            "№ проверки",
            "Тип",
            "Объект",
            "Предмет",
            "Дата",
            "Инспектор",
            "Статус",
            "Нарушения",
        ]
    ]
    for i in qs:
        obj = i.building.address if i.building_id else i.counterparty_name
        insp = ""
        if i.inspector:
            insp = i.inspector.get_full_name() or i.inspector.username
        rows.append(
            [
                i.inspection_number,
                i.get_inspection_type_display(),
                obj,
                i.check_subject,
                i.planned_date.strftime("%d.%m.%Y"),
                insp,
                i.get_status_display(),
                "да" if i.violations_found else "нет",
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_inspections_{stamp}.csv", rows)


def export_interagency_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingInteragencyRequest.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("citizen", "housing_case")
        .order_by("-sent_at")
    )
    rows = [
        [
            "№ запроса",
            "Тип",
            "Адресат",
            "Тема",
            "Дело",
            "Отправлен",
            "Срок",
            "Статус",
        ]
    ]
    for r in qs:
        rows.append(
            [
                r.request_number,
                r.get_request_type_display(),
                r.recipient_name,
                r.subject,
                r.housing_case.case_number if r.housing_case_id else "",
                r.sent_at.strftime("%d.%m.%Y"),
                r.due_date.strftime("%d.%m.%Y"),
                r.get_status_display(),
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_interagency_{stamp}.csv", rows)


def bulk_set_inspection_status(subsystem, ids: list[int], status: str) -> int:
    if status not in dict(HousingInspection.Status.choices):
        return 0
    return HousingInspection.objects.filter(subsystem=subsystem, pk__in=ids).update(
        status=status, updated_at=timezone.now()
    )


def bulk_set_interagency_status(subsystem, ids: list[int], status: str) -> int:
    if status not in dict(HousingInteragencyRequest.Status.choices):
        return 0
    return HousingInteragencyRequest.objects.filter(subsystem=subsystem, pk__in=ids).update(
        status=status, updated_at=timezone.now()
    )


def subsystem_assignees(subsystem):
    from django.contrib.auth import get_user_model

    from delayu.models import SubsystemMembership

    User = get_user_model()
    user_ids = SubsystemMembership.objects.filter(subsystem=subsystem).values_list(
        "user_id", flat=True
    )
    return User.objects.filter(pk__in=user_ids, is_active=True).order_by(
        "last_name", "first_name", "username"
    )


def bulk_set_case_assignee(subsystem, ids: list[int], user_id: int | None) -> int:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    assignee = None
    if user_id:
        assignee = User.objects.filter(
            pk=user_id,
            subsystem_memberships__subsystem=subsystem,
            is_active=True,
        ).first()
        if not assignee:
            return 0
    return HousingQueueCase.objects.filter(subsystem=subsystem, pk__in=ids).update(
        assignee=assignee, updated_at=timezone.now()
    )


def bulk_set_appeal_assignee(subsystem, ids: list[int], user_id: int | None) -> int:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    assignee = None
    if user_id:
        assignee = User.objects.filter(
            pk=user_id,
            subsystem_memberships__subsystem=subsystem,
            is_active=True,
        ).first()
        if not assignee:
            return 0
    return HousingAppeal.objects.filter(subsystem=subsystem, pk__in=ids).update(
        assignee=assignee, updated_at=timezone.now()
    )


def export_contracts_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingContract.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("citizen", "premise", "premise__building")
        .order_by("-signed_at")
    )
    rows = [
        [
            "Номер",
            "Тип",
            "Гражданин",
            "Помещение",
            "МКД",
            "Заключён",
            "Действует до",
            "Статус",
        ]
    ]
    for c in qs:
        premise = str(c.premise) if c.premise_id else ""
        bld = c.premise.building.address if c.premise_id else ""
        rows.append(
            [
                c.contract_number,
                c.get_contract_type_display(),
                c.citizen.full_name,
                premise,
                bld,
                c.signed_at.strftime("%d.%m.%Y"),
                c.valid_until.strftime("%d.%m.%Y") if c.valid_until else "",
                "действует" if c.is_active else "закрыт",
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_contracts_{stamp}.csv", rows)


def bulk_close_contracts(subsystem, ids: list[int]) -> int:
    return HousingContract.objects.filter(
        subsystem=subsystem, pk__in=ids, is_active=True
    ).update(is_active=False)


def export_prescriptions_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingPrescription.objects.filter(
            inspection__subsystem=subsystem, pk__in=ids
        )
        .select_related("inspection", "inspection__building")
        .order_by("due_date")
    )
    rows = [
        [
            "№ предписания",
            "Проверка",
            "Объект",
            "Выдано",
            "Срок",
            "Статус",
            "Содержание",
        ]
    ]
    for p in qs:
        obj = ""
        if p.inspection.building_id:
            obj = p.inspection.building.address
        elif p.inspection.counterparty_name:
            obj = p.inspection.counterparty_name
        rows.append(
            [
                p.prescription_number,
                p.inspection.inspection_number,
                obj,
                p.issued_at.strftime("%d.%m.%Y"),
                p.due_date.strftime("%d.%m.%Y"),
                p.get_status_display(),
                p.description[:200],
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_prescriptions_{stamp}.csv", rows)


def bulk_set_prescription_status(subsystem, ids: list[int], status: str) -> int:
    if status not in dict(HousingPrescription.Status.choices):
        return 0
    return HousingPrescription.objects.filter(
        inspection__subsystem=subsystem, pk__in=ids
    ).update(status=status)


def export_court_cases_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingCourtCase.objects.filter(subsystem=subsystem, pk__in=ids)
        .select_related("inspection", "prescription")
        .order_by("-next_hearing_date", "-case_number")
    )
    rows = [
        [
            "№ дела",
            "Суд",
            "Ответчик",
            "Заседание",
            "Проверка",
            "Статус",
            "Адрес проверки",
        ]
    ]
    for c in qs:
        rows.append(
            [
                c.case_number,
                c.court_name,
                c.defendant_name,
                c.next_hearing_date.strftime("%d.%m.%Y") if c.next_hearing_date else "",
                c.inspection.inspection_number if c.inspection_id else "",
                c.get_status_display(),
                c.check_address,
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_court_cases_{stamp}.csv", rows)


def bulk_set_court_case_status(subsystem, ids: list[int], status: str) -> int:
    if status not in dict(HousingCourtCase.Status.choices):
        return 0
    return HousingCourtCase.objects.filter(subsystem=subsystem, pk__in=ids).update(
        status=status, updated_at=timezone.now()
    )


def export_citizens_csv(subsystem, ids: list[int], *, user=None) -> HttpResponse:
    from delayu.services.privacy import mask_value, user_may_view_pii

    allow_pii = user_may_view_pii(user) if user else False
    qs = (
        HousingCitizen.objects.filter(subsystem=subsystem, pk__in=ids)
        .annotate(case_count=Count("cases"))
        .order_by("last_name", "first_name")
    )
    rows = [["ФИО", "СНИЛС", "Дата рождения", "Телефон", "E-mail", "Адрес", "Дел"]]
    for c in qs:
        name = c.full_name if allow_pii else mask_value(c.full_name, 1)
        snils = c.snils if allow_pii else mask_value(c.snils, 0)
        phone = c.phone if allow_pii else mask_value(c.phone, 0)
        email = c.email if allow_pii else mask_value(c.email, 0)
        address = c.reg_address if allow_pii else mask_value(c.reg_address, 0)
        rows.append(
            [
                name,
                snils,
                c.birth_date.strftime("%d.%m.%Y") if c.birth_date else "",
                phone,
                email,
                address,
                c.case_count,
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_citizens_{stamp}.csv", rows)


def export_young_families_csv(subsystem, case_ids: list[int]) -> HttpResponse:
    qs = (
        YoungFamilyRecord.objects.filter(
            case__subsystem=subsystem, case_id__in=case_ids
        )
        .select_related("case", "case__citizen")
        .order_by("case__case_number")
    )
    rows = [
        [
            "Дело",
            "Заявитель",
            "Супруг(а)",
            "Детей",
            "Программа",
            "Критерии",
            "Дата брака",
        ]
    ]
    for r in qs:
        rows.append(
            [
                r.case.case_number,
                r.case.citizen.full_name,
                r.spouse_full_name,
                r.children_count,
                r.get_program_display(),
                "да" if r.meets_criteria else "нет",
                r.marriage_date.strftime("%d.%m.%Y") if r.marriage_date else "",
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_young_families_{stamp}.csv", rows)


def bulk_set_young_family_meets_criteria(
    subsystem, case_ids: list[int], *, meets: bool
) -> int:
    return YoungFamilyRecord.objects.filter(
        case__subsystem=subsystem, case_id__in=case_ids
    ).update(meets_criteria=meets)


def bulk_set_young_family_program(
    subsystem, case_ids: list[int], program: str
) -> int:
    if program not in dict(YoungFamilyRecord.Program.choices):
        return 0
    return YoungFamilyRecord.objects.filter(
        case__subsystem=subsystem, case_id__in=case_ids
    ).update(program=program)


def export_orphans_csv(subsystem, case_ids: list[int]) -> HttpResponse:
    qs = (
        OrphanHousingRecord.objects.filter(
            case__subsystem=subsystem, case_id__in=case_ids
        )
        .select_related("case", "case__citizen")
        .order_by("case__case_number")
    )
    rows = [
        [
            "Дело",
            "Гражданин",
            "№ решения Минтруда",
            "Дата решения",
            "Статус",
        ]
    ]
    for r in qs:
        rows.append(
            [
                r.case.case_number,
                r.case.citizen.full_name,
                r.mintrud_decision_number,
                r.mintrud_decision_date.strftime("%d.%m.%Y")
                if r.mintrud_decision_date
                else "",
                r.get_housing_status_display(),
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_orphans_{stamp}.csv", rows)


def bulk_set_orphan_housing_status(
    subsystem, case_ids: list[int], status: str
) -> int:
    if status not in dict(OrphanHousingRecord.HousingStatus.choices):
        return 0
    return OrphanHousingRecord.objects.filter(
        case__subsystem=subsystem, case_id__in=case_ids
    ).update(housing_status=status)


def export_admin_protocols_csv(subsystem, ids: list[int]) -> HttpResponse:
    qs = (
        HousingAdminProtocol.objects.filter(
            inspection__subsystem=subsystem, pk__in=ids
        )
        .select_related("inspection", "inspection__building")
        .order_by("-protocol_date")
    )
    rows = [
        [
            "№ протокола",
            "Дата",
            "Проверка",
            "Статья",
            "Лицо",
            "Штраф",
            "Статус",
        ]
    ]
    for p in qs:
        rows.append(
            [
                p.protocol_number,
                p.protocol_date.strftime("%d.%m.%Y"),
                p.inspection.inspection_number,
                p.legal_article,
                p.violator_name,
                str(p.fine_amount) if p.fine_amount is not None else "",
                p.get_status_display(),
            ]
        )
    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_admin_protocols_{stamp}.csv", rows)


def bulk_set_admin_protocol_status(subsystem, ids: list[int], status: str) -> int:
    if status not in dict(HousingAdminProtocol.Status.choices):
        return 0
    return HousingAdminProtocol.objects.filter(
        inspection__subsystem=subsystem, pk__in=ids
    ).update(status=status)
