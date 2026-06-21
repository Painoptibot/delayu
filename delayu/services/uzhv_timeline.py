"""Хронология событий по учётному делу УЖВ."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from delayu.models_uzhv import HousingQueueCase, MunicipalBuilding


@dataclass
class TimelineEvent:
    date: date
    title: str
    kind: str = "info"
    modal_url: str = ""
    modal_title: str = ""
    link_label: str = ""


def _as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def build_case_timeline(case: HousingQueueCase, *, request=None) -> list[TimelineEvent]:
    from django.urls import reverse

    events: list[TimelineEvent] = [
        TimelineEvent(
            date=_as_date(case.registered_at),
            title=f"Постановка на учёт — {case.get_status_display()}",
            kind="case",
        )
    ]
    from delayu.services.uzhv_case_status import status_display

    for hist in case.status_history.select_related("changed_by").order_by("-changed_at")[:20]:
        who = hist.changed_by.get_username() if hist.changed_by else "система"
        title = f"Статус: {status_display(hist.from_status)} → {status_display(hist.to_status)} ({who})"
        if hist.comment:
            title += f" — {hist.comment[:60]}"
        events.append(
            TimelineEvent(
                date=_as_date(hist.changed_at),
                title=title,
                kind="status",
            )
        )
    if case.updated_at and _as_date(case.updated_at) != _as_date(case.registered_at):
        events.append(
            TimelineEvent(
                date=_as_date(case.updated_at),
                title="Обновление карточки дела",
                kind="case",
            )
        )
    if case.income_verified and case.low_income_calculated_at:
        events.append(
            TimelineEvent(
                date=_as_date(case.low_income_calculated_at),
                title="Расчёт малоимущих выполнен",
                kind="income",
            )
        )
    for appeal in case.appeals.order_by("-received_at")[:10]:
        kind = "warning" if appeal.is_overdue else "appeal"
        url = reverse("uzhv-appeal-modal", kwargs={"pk": appeal.pk})
        events.append(
            TimelineEvent(
                date=_as_date(appeal.received_at),
                title=f"Обращение {appeal.appeal_number}: {appeal.subject[:80]}",
                kind=kind,
                modal_url=url,
                modal_title=f"Обращение {appeal.appeal_number}",
                link_label=appeal.get_status_display(),
            )
        )
    for req in case.interagency_requests.order_by("-sent_at")[:10]:
        kind = "warning" if req.is_overdue else "interagency"
        url = reverse("uzhv-interagency-modal", kwargs={"pk": req.pk})
        events.append(
            TimelineEvent(
                date=_as_date(req.sent_at),
                title=f"Межвед. запрос {req.request_number} → {req.recipient_name[:40]}",
                kind=kind,
                modal_url=url,
                modal_title=f"Запрос {req.request_number}",
                link_label=req.get_status_display(),
            )
        )
    from delayu.models_uzhv import OrphanHousingRecord, YoungFamilyRecord

    yf = YoungFamilyRecord.objects.filter(case=case).first()
    if yf:
        events.append(
            TimelineEvent(
                date=_as_date(case.registered_at),
                title=f"Молодая семья — {yf.get_program_display()}",
                kind="category",
            )
        )
    rec = OrphanHousingRecord.objects.filter(case=case).first()
    if rec and rec.mintrud_decision_date:
        events.append(
            TimelineEvent(
                date=_as_date(rec.mintrud_decision_date),
                title=f"Решение Минтруда № {rec.mintrud_decision_number or '—'}",
                kind="category",
            )
        )
    for ct in case.citizen.contracts.filter(is_active=True).order_by("-signed_at")[:5]:
        url = reverse("uzhv-contract-modal", kwargs={"pk": ct.pk})
        events.append(
            TimelineEvent(
                date=_as_date(ct.signed_at),
                title=f"Договор {ct.contract_number} ({ct.get_contract_type_display()})",
                kind="contract",
                modal_url=url,
                modal_title=f"Договор {ct.contract_number}",
                link_label="действует" if ct.is_active else "закрыт",
            )
        )
    if case.status == HousingQueueCase.Status.REMOVED and case.removed_at:
        events.append(
            TimelineEvent(
                date=_as_date(case.removed_at),
                title=f"Снят с учёта: {case.get_removal_reason_display() or '—'}",
                kind="warning",
            )
        )
    events.sort(key=lambda e: e.date, reverse=True)
    return events


def build_citizen_timeline(citizen, *, request=None) -> list[TimelineEvent]:
    from django.urls import reverse

    events: list[TimelineEvent] = [
        TimelineEvent(
            date=_as_date(citizen.created_at),
            title="Карточка гражданина создана",
            kind="info",
        )
    ]
    for case in citizen.cases.order_by("-registered_at")[:15]:
        url = reverse("uzhv-case-modal", kwargs={"pk": case.pk})
        events.append(
            TimelineEvent(
                date=_as_date(case.registered_at),
                title=f"Дело {case.case_number} — {case.get_category_display()}",
                kind="case",
                modal_url=url,
                modal_title=f"Дело {case.case_number}",
                link_label=case.get_status_display(),
            )
        )
    for appeal in citizen.appeals.order_by("-received_at")[:15]:
        kind = "warning" if appeal.is_overdue else "appeal"
        url = reverse("uzhv-appeal-modal", kwargs={"pk": appeal.pk})
        events.append(
            TimelineEvent(
                date=_as_date(appeal.received_at),
                title=f"Обращение {appeal.appeal_number}: {appeal.subject[:80]}",
                kind=kind,
                modal_url=url,
                modal_title=f"Обращение {appeal.appeal_number}",
                link_label=appeal.get_status_display(),
            )
        )
    for req in citizen.interagency_requests.order_by("-sent_at")[:10]:
        kind = "warning" if req.is_overdue else "interagency"
        url = reverse("uzhv-interagency-modal", kwargs={"pk": req.pk})
        events.append(
            TimelineEvent(
                date=_as_date(req.sent_at),
                title=f"Межвед. запрос {req.request_number} → {req.recipient_name[:40]}",
                kind=kind,
                modal_url=url,
                modal_title=f"Запрос {req.request_number}",
                link_label=req.get_status_display(),
            )
        )
    for ct in citizen.contracts.order_by("-signed_at")[:10]:
        url = reverse("uzhv-contract-modal", kwargs={"pk": ct.pk})
        events.append(
            TimelineEvent(
                date=_as_date(ct.signed_at),
                title=f"Договор {ct.contract_number} ({ct.get_contract_type_display()})",
                kind="contract",
                modal_url=url,
                modal_title=f"Договор {ct.contract_number}",
                link_label="действует" if ct.is_active else "закрыт",
            )
        )
    if citizen.updated_at and _as_date(citizen.updated_at) != _as_date(citizen.created_at):
        events.append(
            TimelineEvent(
                date=_as_date(citizen.updated_at),
                title="Обновление карточки гражданина",
                kind="info",
            )
        )
    events.sort(key=lambda e: e.date, reverse=True)
    return events


def build_building_timeline(building: MunicipalBuilding, *, request=None) -> list[TimelineEvent]:
    from django.urls import reverse

    from delayu.models_uzhv import HousingContract, HousingPrescription

    events: list[TimelineEvent] = [
        TimelineEvent(
            date=_as_date(building.created_at),
            title=f"Объект внесён в реестр — {building.get_condition_display()}",
            kind="info",
        )
    ]
    if building.in_resettlement_program:
        events.append(
            TimelineEvent(
                date=_as_date(building.created_at),
                title="Включён в программу расселения (4779)",
                kind="warning",
            )
        )
    for insp in building.inspections.order_by("-planned_date")[:12]:
        kind = "warning" if insp.violations_found else "inspection"
        url = reverse("uzhv-inspection-modal", kwargs={"pk": insp.pk})
        obj = insp.check_subject[:60] if insp.check_subject else insp.get_inspection_type_display()
        events.append(
            TimelineEvent(
                date=_as_date(insp.planned_date),
                title=f"Проверка {insp.inspection_number}: {obj}",
                kind=kind,
                modal_url=url,
                modal_title=f"Проверка {insp.inspection_number}",
                link_label=insp.get_status_display(),
            )
        )
    for p in (
        HousingPrescription.objects.filter(inspection__building=building)
        .select_related("inspection")
        .order_by("-issued_at")[:10]
    ):
        kind = "warning" if p.is_overdue else "prescription"
        url = reverse("uzhv-prescription-modal", kwargs={"pk": p.pk})
        events.append(
            TimelineEvent(
                date=_as_date(p.issued_at),
                title=f"Предписание {p.prescription_number}: {p.description[:60]}",
                kind=kind,
                modal_url=url,
                modal_title=f"Предписание {p.prescription_number}",
                link_label=p.get_status_display(),
            )
        )
    for ct in (
        HousingContract.objects.filter(premise__building=building)
        .select_related("citizen", "premise")
        .order_by("-signed_at")[:10]
    ):
        url = reverse("uzhv-contract-modal", kwargs={"pk": ct.pk})
        events.append(
            TimelineEvent(
                date=_as_date(ct.signed_at),
                title=f"Договор {ct.contract_number} — {ct.citizen.full_name}",
                kind="contract",
                modal_url=url,
                modal_title=f"Договор {ct.contract_number}",
                link_label="действует" if ct.is_active else "закрыт",
            )
        )
    events.sort(key=lambda e: e.date, reverse=True)
    return events
