"""Отчёты АИС УЖВ — выгрузки по формам ТЗ и шаблонам заказчика."""
from __future__ import annotations

import csv
import io
from datetime import date

from django.db.models import Q
from django.utils import timezone

from delayu.models_uzhv import (
    HousingAppeal,
    HousingContract,
    HousingCourtCase,
    HousingInspection,
    HousingInspectionOrder,
    HousingEnforcementProceeding,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
    MunicipalPremise,
    OrphanHousingRecord,
)


def _csv_response_rows(rows: list[list], delimiter=";") -> str:
    buf = io.StringIO()
    buf.write("\ufeff")  # Excel UTF-8 BOM
    writer = csv.writer(buf, delimiter=delimiter, lineterminator="\r\n")
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def report_otch1_queue(subsystem) -> str:
    """ОТЧ-1 — список граждан на учёте (по запросу)."""
    rows = [
        [
            "№ п/п",
            "ФИО",
            "СНИЛС",
            "Номер дела",
            "Категория",
            "Дата постановки",
            "Очерёдность",
            "Статус",
            "Исполнитель",
        ]
    ]
    qs = (
        HousingQueueCase.objects.filter(
            subsystem=subsystem,
            status__in=[
                HousingQueueCase.Status.REGISTERED,
                HousingQueueCase.Status.QUEUED,
            ],
        )
        .select_related("citizen", "assignee")
        .order_by("queue_position", "registered_at")
    )
    for i, c in enumerate(qs, 1):
        rows.append(
            [
                i,
                c.citizen.full_name,
                c.citizen.snils,
                c.case_number,
                c.get_category_display(),
                c.registered_at.strftime("%d.%m.%Y"),
                c.queue_position or "",
                c.get_status_display(),
                (c.assignee.get_full_name() if c.assignee else "") or "",
            ]
        )
    return _csv_response_rows(rows)


def report_otch2_provided(subsystem, period_start: date | None, period_end: date | None) -> str:
    """ОТЧ-2 / Приложение — предоставленные жилые помещения за период."""
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, 1, 1)
    rows = [
        [
            "№ п/п",
            "Ф.И.О. нанимателя",
            "Адрес помещения",
            "Площадь",
            "Комнат",
            "Вид фонда",
            "Вид договора",
            "Дата договора",
            "Номер договора",
            "Срок действия",
        ]
    ]
    qs = (
        HousingContract.objects.filter(
            subsystem=subsystem,
            signed_at__gte=period_start,
            signed_at__lte=period_end,
            is_active=True,
        )
        .select_related("citizen", "premise", "premise__building")
        .order_by("signed_at")
    )
    for i, c in enumerate(qs, 1):
        addr = str(c.premise) if c.premise else ""
        rows.append(
            [
                i,
                c.citizen.full_name,
                addr,
                c.premise.area_sqm if c.premise else "",
                c.premise.rooms if c.premise else "",
                "муниципальный",
                c.get_contract_type_display(),
                c.signed_at.strftime("%d.%m.%Y"),
                c.contract_number,
                c.valid_until.strftime("%d.%m.%Y") if c.valid_until else "",
            ]
        )
    return _csv_response_rows(rows)


def report_otch3_contracts_gorzhilkhoz(subsystem) -> str:
    """ОТЧ-3 — реестр договоров (колонки как в xlsx «Горжилхоз»)."""
    rows = [
        [
            "№ п/п",
            "Тип договора",
            "Номер договора",
            "Дата заключения",
            "Фамилия",
            "Имя",
            "Отчество",
            "Адрес ОЖФ",
        ]
    ]
    qs = HousingContract.objects.filter(subsystem=subsystem, is_active=True).select_related(
        "citizen", "premise", "premise__building"
    )
    for i, c in enumerate(qs.order_by("-signed_at"), 1):
        ct = c.citizen
        rows.append(
            [
                i,
                c.get_contract_type_display(),
                c.contract_number,
                c.signed_at.strftime("%d.%m.%Y"),
                ct.last_name,
                ct.first_name,
                ct.middle_name,
                str(c.premise) if c.premise else "",
            ]
        )
    return _csv_response_rows(rows)


def report_otch5_appeals(subsystem, period_start: date | None, period_end: date | None) -> str:
    """ОТЧ-5 — статистика обращений за период."""
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, period_end.month, 1)
    qs = HousingAppeal.objects.filter(
        subsystem=subsystem,
        received_at__gte=period_start,
        received_at__lte=period_end,
    )
    today = timezone.now().date()
    open_qs = qs.exclude(
        status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
    )
    rows = [
        ["Показатель", "Значение"],
        ["Период с", period_start.strftime("%d.%m.%Y")],
        ["Период по", period_end.strftime("%d.%m.%Y")],
        ["Всего обращений", qs.count()],
        ["В работе", open_qs.count()],
        ["Ответ дан", qs.filter(status=HousingAppeal.Status.ANSWERED).count()],
        ["Закрыто", qs.filter(status=HousingAppeal.Status.CLOSED).count()],
        [
            "Просрочено",
            open_qs.filter(due_date__lt=today).count(),
        ],
    ]
    return _csv_response_rows(rows)


def report_otch6_fund_movement(subsystem, period_start: date | None, period_end: date | None) -> str:
    """ОТЧ-6 — движение жилфонда (форма приложения ТЗ)."""
    from delayu.services.uzhv_report_forms import build_otch6_rows

    _, rows = build_otch6_rows(subsystem, period_start, period_end)
    return _csv_response_rows(rows)


def report_otch4_inspections(subsystem, period_start: date | None, period_end: date | None) -> str:
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, period_end.month, 1)
    rows = [
        [
            "№ проверки",
            "Тип",
            "Объект",
            "Адрес/наименование",
            "Предмет",
            "Дата",
            "Статус",
            "Нарушения",
            "Предписаний об устранении",
            "Протоколы АП",
            "№ предписания на проверку",
            "План",
        ]
    ]
    qs = HousingInspection.objects.filter(
        subsystem=subsystem,
        planned_date__gte=period_start,
        planned_date__lte=period_end,
    ).select_related("building", "inspector", "plan", "conduct_order")
    for i in qs.order_by("planned_date"):
        addr = i.building.address if i.building else i.counterparty_name
        try:
            order_no = i.conduct_order.order_number
        except HousingInspectionOrder.DoesNotExist:
            order_no = ""
        rows.append(
            [
                i.inspection_number,
                i.get_inspection_type_display(),
                i.get_object_type_display(),
                addr,
                i.check_subject,
                i.planned_date.strftime("%d.%m.%Y"),
                i.get_status_display(),
                "Да" if i.violations_found else "Нет",
                i.prescriptions.count(),
                i.admin_protocols.count(),
                order_no,
                i.plan.plan_number if i.plan_id else "",
            ]
        )
    return _csv_response_rows(rows)


def report_otch7_orphans(subsystem) -> str:
    rows = [
        [
            "№ дела",
            "ФИО",
            "Статус реализации прав",
            "№ решения Минтруда",
            "Дата решения",
            "Примечание",
        ]
    ]
    qs = OrphanHousingRecord.objects.filter(case__subsystem=subsystem).select_related(
        "case", "case__citizen"
    )
    for r in qs.order_by("case__case_number"):
        rows.append(
            [
                r.case.case_number,
                r.case.citizen.full_name,
                r.get_housing_status_display(),
                r.mintrud_decision_number,
                r.mintrud_decision_date.strftime("%d.%m.%Y") if r.mintrud_decision_date else "",
                r.notes[:200],
            ]
        )
    return _csv_response_rows(rows)


def report_otch9_resettlement(subsystem) -> str:
    """ОТЧ-9 — программа расселения аварийного фонда (4779)."""
    from delayu.services.uzhv_report_forms import build_otch9_rows

    _, rows = build_otch9_rows(subsystem)
    return _csv_response_rows(rows)


def report_unfit_premises(subsystem) -> str:
    """Реестр непригодных жилых помещений (ТЗ п. 347)."""
    rows = [
        [
            "№ п/п",
            "Адрес МКД",
            "№ помещения",
            "Площадь, м²",
            "№ акта / решения",
            "Дата признания",
            "Основание",
            "Пригодность по назначению",
            "Спец. (сироты)",
        ]
    ]
    qs = (
        MunicipalPremise.objects.filter(
            building__subsystem=subsystem, unfit_for_living=True
        )
        .select_related("building")
        .order_by("building__address", "number")
    )
    for i, p in enumerate(qs, 1):
        rows.append(
            [
                i,
                p.building.address,
                p.number,
                p.area_sqm or "",
                p.unfit_decision_ref,
                p.unfit_decision_at.strftime("%d.%m.%Y") if p.unfit_decision_at else "",
                p.unfit_reason[:200] if p.unfit_reason else "",
                "Да" if p.usable_for_purpose else "Нет",
                "Да" if p.specialized_orphan else "Нет",
            ]
        )
    return _csv_response_rows(rows)


def report_otch10_compliance(subsystem, period_start: date | None, period_end: date | None) -> str:
    """ОТЧ-10 — исполнение предписаний и судебных актов за период."""
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, period_end.month, 1)
    rows = [
        [
            "Раздел",
            "№",
            "Проверка",
            "Объект / ответчик",
            "Срок / заседание",
            "Статус",
            "Исполнено",
            "УФССП / примечание",
        ]
    ]
    prescriptions = HousingPrescription.objects.filter(
        inspection__subsystem=subsystem,
        issued_at__gte=period_start,
        issued_at__lte=period_end,
    ).select_related("inspection", "inspection__building")
    for p in prescriptions.order_by("issued_at"):
        addr = ""
        if p.inspection.building:
            addr = p.inspection.building.address
        elif p.inspection.counterparty_name:
            addr = p.inspection.counterparty_name
        rows.append(
            [
                "Предписание об устранении",
                p.prescription_number,
                p.inspection.inspection_number,
                addr,
                p.due_date.strftime("%d.%m.%Y"),
                p.get_status_display(),
                p.fulfilled_at.strftime("%d.%m.%Y") if p.fulfilled_at else "",
                p.description[:120],
            ]
        )
    court_cases = HousingCourtCase.objects.filter(
        subsystem=subsystem,
    ).filter(
        Q(next_hearing_date__gte=period_start, next_hearing_date__lte=period_end)
        | Q(created_at__date__gte=period_start, created_at__date__lte=period_end)
    ).select_related("inspection", "prescription")
    for c in court_cases.order_by("next_hearing_date", "case_number"):
        rows.append(
            [
                "Судебное дело",
                c.case_number,
                c.inspection.inspection_number if c.inspection else "",
                c.defendant_name or c.check_address,
                c.next_hearing_date.strftime("%d.%m.%Y") if c.next_hearing_date else "",
                c.get_status_display(),
                "",
                c.ufssp_reference or c.notes[:120],
            ]
        )
    orders = HousingInspectionOrder.objects.filter(
        subsystem=subsystem,
        issued_at__gte=period_start,
        issued_at__lte=period_end,
    ).select_related("building", "inspection", "plan")
    for o in orders.order_by("issued_at"):
        addr = o.building.address if o.building else o.check_address or o.addressee
        rows.append(
            [
                "Предписание на проверку",
                o.order_number,
                o.inspection.inspection_number if o.inspection_id else "",
                addr,
                o.conduct_by.strftime("%d.%m.%Y"),
                o.get_status_display(),
                o.inspection.completed_date.strftime("%d.%m.%Y")
                if o.inspection_id and o.inspection.completed_date
                else "",
                o.plan.plan_number if o.plan_id else o.notes[:120],
            ]
        )
    enforcements = HousingEnforcementProceeding.objects.filter(
        subsystem=subsystem,
        initiated_at__gte=period_start,
        initiated_at__lte=period_end,
    ).select_related("court_case")
    for e in enforcements.order_by("initiated_at"):
        rows.append(
            [
                "Исп. производство",
                e.proceeding_number,
                e.court_case.case_number,
                e.debtor_name,
                e.initiated_at.strftime("%d.%m.%Y"),
                e.get_status_display(),
                e.completed_at.strftime("%d.%m.%Y") if e.completed_at else "",
                e.bailiff_office or e.court_decision[:120],
            ]
        )
    return _csv_response_rows(rows)


def report_otch8_interagency(subsystem, period_start: date | None, period_end: date | None) -> str:
    """ОТЧ-8 — межведомственные запросы и сроки ответов (ручной учёт)."""
    period_end = period_end or timezone.now().date()
    period_start = period_start or date(period_end.year, period_end.month, 1)
    rows = [
        [
            "№ запроса",
            "Тип",
            "Адресат",
            "Канал",
            "Тема",
            "ФИО / дело",
            "Отправлен",
            "Срок ответа",
            "Ответ получен",
            "Статус",
            "Результат",
        ]
    ]
    qs = HousingInteragencyRequest.objects.filter(
        subsystem=subsystem,
        sent_at__gte=period_start,
        sent_at__lte=period_end,
    ).select_related("citizen", "housing_case")
    for r in qs.order_by("sent_at"):
        case_ref = r.citizen.full_name if r.citizen else ""
        if r.housing_case:
            case_ref = f"{case_ref} / {r.housing_case.case_number}".strip(" /")
        rows.append(
            [
                r.request_number,
                r.get_request_type_display(),
                r.recipient_name,
                r.get_channel_display(),
                r.subject[:120],
                case_ref,
                r.sent_at.strftime("%d.%m.%Y"),
                r.due_date.strftime("%d.%m.%Y"),
                r.answered_at.strftime("%d.%m.%Y") if r.answered_at else "",
                r.get_status_display(),
                r.response_summary[:200],
            ]
        )
    return _csv_response_rows(rows)


def report_workload_assignees(subsystem) -> str:
    """Сводка нагрузки по исполнителям (открытые дела и просрочки)."""
    from delayu.services.uzhv_workload import assignee_workload_csv_rows

    return _csv_response_rows(assignee_workload_csv_rows(subsystem))


REPORT_BUILDERS = {
    "otch-1": ("ОТЧ-1 — Список на учёте", report_otch1_queue, False),
    "otch-2": ("ОТЧ-2 — Предоставление жилья", report_otch2_provided, True),
    "otch-3": ("ОТЧ-3 — Договоры (Горжилхоз)", report_otch3_contracts_gorzhilkhoz, False),
    "otch-4": ("ОТЧ-4 — Результаты проверок", report_otch4_inspections, True),
    "otch-5": ("ОТЧ-5 — Обращения", report_otch5_appeals, True),
    "otch-6": ("ОТЧ-6 — Движение жилфонда", report_otch6_fund_movement, True),
    "otch-7": ("ОТЧ-7 — Дети-сироты", report_otch7_orphans, False),
    "otch-8": ("ОТЧ-8 — Межведомственные запросы", report_otch8_interagency, True),
    "otch-9": ("ОТЧ-9 — Расселение аварийного фонда", report_otch9_resettlement, False),
    "unfit-premises": ("Непригодные помещения", report_unfit_premises, False),
    "otch-10": ("ОТЧ-10 — Исполнение предписаний", report_otch10_compliance, True),
    "workload": ("Нагрузка по исполнителям", report_workload_assignees, False),
}

