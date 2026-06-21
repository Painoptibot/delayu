"""Сводка просроченных сроков АИС УЖВ с фильтром по исполнителю."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from delayu.models_uzhv import (
    HousingAppeal,
    HousingInteragencyRequest,
    HousingPrescription,
)


@dataclass
class OverdueItem:
    date: date
    kind: str
    type_label: str
    title: str
    assignee_label: str
    modal_url: str
    modal_title: str
    days_overdue: int


def _assignee_name(user) -> str:
    if not user:
        return "—"
    return user.get_full_name() or user.username


def interagency_assignee_q(assignee_id: int) -> Q:
    return Q(housing_case__assignee_id=assignee_id) | Q(
        housing_case__isnull=True, created_by_id=assignee_id
    ) | Q(housing_case__assignee__isnull=True, created_by_id=assignee_id)


def filter_prescriptions_assignee(qs, assignee_id: int | None):
    if assignee_id:
        return qs.filter(inspection__inspector_id=assignee_id)
    return qs


def filter_interagency_assignee(qs, assignee_id: int | None):
    if assignee_id:
        return qs.filter(interagency_assignee_q(assignee_id))
    return qs


def list_overdue_items(
    subsystem, *, assignee_id: int | None = None, limit: int | None = 25
) -> list[OverdueItem]:
    """Просроченные обращения, предписания и межвед. запросы, опционально по исполнителю."""
    today = timezone.now().date()
    items: list[OverdueItem] = []

    appeals = (
        HousingAppeal.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
        )
        .filter(due_date__lt=today)
        .select_related("assignee", "citizen")
    )
    if assignee_id:
        appeals = appeals.filter(assignee_id=assignee_id)

    for a in appeals:
        items.append(
            OverdueItem(
                date=a.due_date,
                kind="appeal",
                type_label="Обращение",
                title=f"{a.appeal_number} — {a.subject[:55]}",
                assignee_label=_assignee_name(a.assignee),
                modal_url=reverse("uzhv-appeal-modal", kwargs={"pk": a.pk}),
                modal_title=f"Обращение {a.appeal_number}",
                days_overdue=(today - a.due_date).days,
            )
        )

    prescriptions = (
        HousingPrescription.objects.filter(inspection__subsystem=subsystem)
        .exclude(
            status__in=[
                HousingPrescription.Status.FULFILLED,
                HousingPrescription.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today)
        .select_related("inspection", "inspection__inspector", "inspection__building")
    )
    if assignee_id:
        prescriptions = prescriptions.filter(inspection__inspector_id=assignee_id)

    for p in prescriptions:
        items.append(
            OverdueItem(
                date=p.due_date,
                kind="prescription",
                type_label="Предписание",
                title=f"{p.prescription_number} — {p.description[:50]}",
                assignee_label=_assignee_name(
                    p.inspection.inspector if p.inspection_id else None
                ),
                modal_url=reverse("uzhv-prescription-modal", kwargs={"pk": p.pk}),
                modal_title=f"Предписание {p.prescription_number}",
                days_overdue=(today - p.due_date).days,
            )
        )

    interagency = (
        HousingInteragencyRequest.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingInteragencyRequest.Status.ANSWERED,
                HousingInteragencyRequest.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today)
        .select_related("housing_case", "housing_case__assignee", "created_by")
    )
    if assignee_id:
        interagency = filter_interagency_assignee(interagency, assignee_id)

    for r in interagency:
        user = None
        if r.housing_case_id and r.housing_case.assignee_id:
            user = r.housing_case.assignee
        elif r.created_by_id:
            user = r.created_by
        items.append(
            OverdueItem(
                date=r.due_date,
                kind="interagency",
                type_label="Межвед.",
                title=f"{r.request_number} — {r.recipient_name[:45]}",
                assignee_label=_assignee_name(user),
                modal_url=reverse("uzhv-interagency-modal", kwargs={"pk": r.pk}),
                modal_title=f"Запрос {r.request_number}",
                days_overdue=(today - r.due_date).days,
            )
        )

    items.sort(key=lambda x: (-x.days_overdue, x.date))
    if limit is not None:
        return items[:limit]
    return items


def _overdue_export_rows(subsystem, *, assignee_id: int | None = None) -> list[list]:
    items = list_overdue_items(subsystem, assignee_id=assignee_id, limit=None)
    rows = [
        [
            "Тип",
            "Событие",
            "Срок",
            "Дней просрочки",
            "Исполнитель",
        ]
    ]
    for item in items:
        rows.append(
            [
                item.type_label,
                item.title,
                item.date.strftime("%d.%m.%Y"),
                item.days_overdue,
                item.assignee_label,
            ]
        )
    return rows


def export_overdue_csv(subsystem, *, assignee_id: int | None = None):
    from delayu.services.uzhv_bulk import _csv_response

    stamp = timezone.now().strftime("%Y%m%d")
    return _csv_response(f"uzhv_overdue_{stamp}.csv", _overdue_export_rows(subsystem, assignee_id=assignee_id))


def export_overdue_xlsx(subsystem, *, assignee_id: int | None = None):
    from delayu.services.uzhv_export import rows_to_xlsx_bytes

    rows = _overdue_export_rows(subsystem, assignee_id=assignee_id)
    stamp = timezone.now().strftime("%Y%m%d")
    content = rows_to_xlsx_bytes(rows, sheet_title="Просрочки")
    resp = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="uzhv_overdue_{stamp}.xlsx"'
    return resp


def parse_hub_assignee_filter(params, user) -> int | None:
    raw = (params.get("assignee") or "").strip()
    if raw == "me" and user and user.is_authenticated:
        return user.pk
    if raw.isdigit():
        return int(raw)
    return None
