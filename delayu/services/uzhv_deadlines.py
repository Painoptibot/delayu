"""Ближайшие сроки и дедлайны АИС УЖВ для hub и отчётов."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta

from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone

from delayu.models_uzhv import (
    HousingAppeal,
    HousingCourtCase,
    HousingInspectionOrder,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
)

KIND_COLORS = {
    "appeal": "#ff4c51",
    "prescription": "#ff9f43",
    "interagency": "#7367f0",
    "court": "#00cfe8",
    "low_income": "#28c76f",
    "inspection_order": "#ea5455",
}


@dataclass
class DeadlineItem:
    date: date
    kind: str
    type_label: str
    title: str
    modal_url: str
    modal_title: str
    is_overdue: bool = False
    list_url: str = ""


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _collect_deadlines(
    subsystem,
    start: date,
    until: date,
    *,
    limit: int | None = None,
) -> list[DeadlineItem]:
    today = timezone.now().date()
    items: list[DeadlineItem] = []

    appeals = (
        HousingAppeal.objects.filter(subsystem=subsystem)
        .exclude(status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED])
        .filter(due_date__gte=start, due_date__lte=until)
        .select_related("citizen")
        .order_by("due_date")
    )
    for a in appeals:
        items.append(
            DeadlineItem(
                date=a.due_date,
                kind="appeal",
                type_label="Обращение",
                title=f"{a.appeal_number} — {a.subject[:50]}",
                modal_url=reverse("uzhv-appeal-modal", kwargs={"pk": a.pk}),
                modal_title=f"Обращение {a.appeal_number}",
                is_overdue=a.due_date < today,
                list_url=reverse("uzhv-appeals") + f"?open={a.pk}",
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
        .filter(due_date__gte=start, due_date__lte=until)
        .select_related("inspection", "inspection__building")
        .order_by("due_date")
    )
    for p in prescriptions:
        items.append(
            DeadlineItem(
                date=p.due_date,
                kind="prescription",
                type_label="Предписание",
                title=f"{p.prescription_number} — {p.description[:50]}",
                modal_url=reverse("uzhv-prescription-modal", kwargs={"pk": p.pk}),
                modal_title=f"Предписание {p.prescription_number}",
                is_overdue=p.due_date < today,
                list_url=reverse("uzhv-prescriptions") + f"?open={p.pk}",
            )
        )

    conduct_orders = (
        HousingInspectionOrder.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingInspectionOrder.Status.COMPLETED,
                HousingInspectionOrder.Status.CANCELLED,
            ]
        )
        .filter(conduct_by__gte=start, conduct_by__lte=until)
        .order_by("conduct_by")
    )
    for o in conduct_orders:
        items.append(
            DeadlineItem(
                date=o.conduct_by,
                kind="inspection_order",
                type_label="Предписание на проверку",
                title=f"{o.order_number} — {o.addressee[:40]}",
                modal_url="",
                modal_title="",
                is_overdue=o.conduct_by < today,
                list_url=reverse("uzhv-inspection-order-edit", kwargs={"pk": o.pk}),
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
        .filter(due_date__gte=start, due_date__lte=until)
        .order_by("due_date")
    )
    for r in interagency:
        items.append(
            DeadlineItem(
                date=r.due_date,
                kind="interagency",
                type_label="Межвед",
                title=f"{r.request_number} → {r.recipient_name[:40]}",
                modal_url=reverse("uzhv-interagency-modal", kwargs={"pk": r.pk}),
                modal_title=f"Запрос {r.request_number}",
                is_overdue=r.due_date < today,
                list_url=reverse("uzhv-interagency") + f"?open={r.pk}",
            )
        )

    court_cases = (
        HousingCourtCase.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingCourtCase.Status.CLOSED,
                HousingCourtCase.Status.CANCELLED,
            ]
        )
        .filter(
            next_hearing_date__isnull=False,
            next_hearing_date__gte=start,
            next_hearing_date__lte=until,
        )
        .order_by("next_hearing_date")
    )
    for c in court_cases:
        items.append(
            DeadlineItem(
                date=c.next_hearing_date,
                kind="court",
                type_label="Суд",
                title=f"{c.case_number} — {c.court_name[:40]}",
                modal_url=reverse("uzhv-court-case-modal", kwargs={"pk": c.pk}),
                modal_title=f"Дело {c.case_number}",
                is_overdue=c.next_hearing_date < today,
                list_url=reverse("uzhv-court-cases") + f"?open={c.pk}",
            )
        )

    low_income_cases = (
        HousingQueueCase.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingQueueCase.Status.PROVIDED,
                HousingQueueCase.Status.REMOVED,
                HousingQueueCase.Status.REJECTED,
            ]
        )
        .filter(
            low_income_review_due_at__isnull=False,
            low_income_review_due_at__gte=start,
            low_income_review_due_at__lte=until,
            low_income_eligible__isnull=True,
        )
        .select_related("citizen")
        .order_by("low_income_review_due_at")
    )
    for case in low_income_cases:
        items.append(
            DeadlineItem(
                date=case.low_income_review_due_at,
                kind="low_income",
                type_label="Малоимущие",
                title=f"{case.case_number} — {case.citizen.full_name[:40]}",
                modal_url=reverse("uzhv-case-modal", kwargs={"pk": case.pk}),
                modal_title=f"Дело {case.case_number}",
                is_overdue=case.low_income_review_due_at < today,
                list_url=reverse("uzhv-case-low-income", kwargs={"pk": case.pk}),
            )
        )

    items.sort(key=lambda x: (x.date, x.kind))
    if limit is not None:
        return items[:limit]
    return items


def upcoming_deadlines(subsystem, *, days: int = 7, limit: int = 12) -> list[DeadlineItem]:
    today = timezone.now().date()
    return _collect_deadlines(
        subsystem,
        today - timedelta(days=90),
        today + timedelta(days=days),
        limit=limit,
    )


def deadlines_grouped(
    subsystem, *, start: date | None = None, days: int = 7
) -> list[tuple[date, list[DeadlineItem]]]:
    if start is None:
        start = _week_start(timezone.now().date())
    until = start + timedelta(days=days - 1)
    by_day: dict[date, list[DeadlineItem]] = {}
    for offset in range(days):
        by_day[start + timedelta(days=offset)] = []
    for item in _collect_deadlines(subsystem, start, until):
        by_day.setdefault(item.date, []).append(item)
    return sorted(by_day.items())


def deadlines_as_calendar_events(
    subsystem, *, start: date, days: int = 7
) -> list[dict]:
    until = start + timedelta(days=days - 1)
    events = []
    for item in _collect_deadlines(subsystem, start, until):
        color = KIND_COLORS.get(item.kind, "#7367f0")
        events.append(
            {
                "id": f"{item.kind}-{item.modal_url}",
                "title": f"{item.type_label}: {item.title[:40]}",
                "start": item.date.isoformat(),
                "allDay": True,
                "url": item.list_url,
                "backgroundColor": color,
                "borderColor": color,
                "textColor": "#fff",
                "classNames": [f"fc-event-uzhv-{item.kind}"],
                "extendedProps": {
                    "calendar": item.kind,
                    "modal_url": item.modal_url,
                    "modal_title": item.modal_title,
                    "overdue": item.is_overdue,
                },
            }
        )
    return events


def month_grid_bounds(day: date) -> tuple[date, date]:
    from calendar import monthrange

    first = day.replace(day=1)
    grid_start = _week_start(first)
    last_day = monthrange(day.year, day.month)[1]
    last = day.replace(day=last_day)
    grid_end = _week_start(last) + timedelta(days=6)
    return grid_start, grid_end


def deadlines_for_month(subsystem, month: date) -> list[dict]:
    grid_start, grid_end = month_grid_bounds(month)
    days = (grid_end - grid_start).days + 1
    return deadlines_as_calendar_events(subsystem, start=grid_start, days=days)


def export_deadlines_csv(subsystem, *, days: int = 30) -> HttpResponse:
    today = timezone.now().date()
    items = _collect_deadlines(
        subsystem, today - timedelta(days=7), today + timedelta(days=days)
    )
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Дата", "Тип", "Событие", "Просрочено"])
    for item in items:
        writer.writerow(
            [
                item.date.strftime("%d.%m.%Y"),
                item.type_label,
                item.title,
                "да" if item.is_overdue else "нет",
            ]
        )
    content = "\ufeff" + buf.getvalue()
    stamp = timezone.now().strftime("%Y%m%d")
    resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="uzhv_deadlines_{stamp}.csv"'
    return resp


def export_deadlines_ical(subsystem, *, days: int = 60) -> HttpResponse:
    """Экспорт сроков в формате iCalendar (.ics)."""
    today = timezone.now().date()
    start = today - timedelta(days=7)
    until = today + timedelta(days=days)
    items = _collect_deadlines(subsystem, start, until)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Delayu UZHV//RU",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for item in items:
        uid = f"uzhv-{item.kind}-{item.modal_url}@delayu"
        dt = item.date.strftime("%Y%m%d")
        summary = _ical_escape(f"{item.type_label}: {item.title[:80]}")
        desc = _ical_escape(item.title)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTART;VALUE=DATE:{dt}",
                f"DTEND;VALUE=DATE:{dt}",
                f"SUMMARY:{summary}",
                f"DESCRIPTION:{desc}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines)
    stamp = timezone.now().strftime("%Y%m%d")
    resp = HttpResponse(body, content_type="text/calendar; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="uzhv_deadlines_{stamp}.ics"'
    return resp


def _ical_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )
