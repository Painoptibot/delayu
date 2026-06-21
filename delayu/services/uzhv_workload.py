"""Сводка нагрузки исполнителей АИС УЖВ."""
from __future__ import annotations

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from delayu.models_uzhv import (
    HousingAppeal,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
)

User = get_user_model()


def _empty_row(name: str) -> dict:
    return {
        "name": name,
        "cases_open": 0,
        "appeals_open": 0,
        "appeals_overdue": 0,
        "prescriptions_overdue": 0,
        "interagency_overdue": 0,
    }


def _total_overdue(row: dict) -> int:
    return (
        row["appeals_overdue"]
        + row["prescriptions_overdue"]
        + row["interagency_overdue"]
    )


def build_assignee_workload(subsystem) -> list[dict]:
    """Агрегированная нагрузка по исполнителям подсистемы."""
    today = timezone.now().date()
    rows: dict[int, dict] = {}

    def ensure(uid: int, name: str):
        if uid not in rows:
            rows[uid] = _empty_row(name)

    appeals = HousingAppeal.objects.filter(subsystem=subsystem).exclude(
        status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
    )
    for item in (
        appeals.filter(assignee_id__isnull=False)
        .values("assignee_id")
        .annotate(c=Count("id"))
    ):
        uid = item["assignee_id"]
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        ensure(uid, user.get_full_name() or user.username)
        rows[uid]["appeals_open"] = item["c"]

    for item in (
        appeals.filter(assignee_id__isnull=False, due_date__lt=today)
        .values("assignee_id")
        .annotate(c=Count("id"))
    ):
        uid = item["assignee_id"]
        if uid in rows:
            rows[uid]["appeals_overdue"] = item["c"]

    for item in (
        HousingQueueCase.objects.filter(
            subsystem=subsystem,
            assignee_id__isnull=False,
            status__in=[
                HousingQueueCase.Status.REGISTERED,
                HousingQueueCase.Status.QUEUED,
            ],
        )
        .values("assignee_id")
        .annotate(c=Count("id"))
    ):
        uid = item["assignee_id"]
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        ensure(uid, user.get_full_name() or user.username)
        rows[uid]["cases_open"] = item["c"]

    pres = (
        HousingPrescription.objects.filter(inspection__subsystem=subsystem)
        .exclude(
            status__in=[
                HousingPrescription.Status.FULFILLED,
                HousingPrescription.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today, inspection__inspector_id__isnull=False)
    )
    for item in pres.values("inspection__inspector_id").annotate(c=Count("id")):
        uid = item["inspection__inspector_id"]
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        ensure(uid, user.get_full_name() or user.username)
        rows[uid]["prescriptions_overdue"] = item["c"]

    inter = (
        HousingInteragencyRequest.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingInteragencyRequest.Status.ANSWERED,
                HousingInteragencyRequest.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today)
    )
    for item in (
        inter.filter(housing_case__assignee_id__isnull=False)
        .values("housing_case__assignee_id")
        .annotate(c=Count("id"))
    ):
        uid = item["housing_case__assignee_id"]
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        ensure(uid, user.get_full_name() or user.username)
        rows[uid]["interagency_overdue"] += item["c"]

    for item in (
        inter.filter(
            Q(housing_case__isnull=True) | Q(housing_case__assignee__isnull=True),
            created_by_id__isnull=False,
        )
        .values("created_by_id")
        .annotate(c=Count("id"))
    ):
        uid = item["created_by_id"]
        user = User.objects.filter(pk=uid).first()
        if not user:
            continue
        ensure(uid, user.get_full_name() or user.username)
        rows[uid]["interagency_overdue"] += item["c"]

    result = []
    for uid, row in rows.items():
        row["user_id"] = uid
        row["total_overdue"] = _total_overdue(row)
        result.append(row)
    result.sort(key=lambda r: (-r["total_overdue"], -r["appeals_open"], r["name"]))
    return result


def assignee_workload_row(subsystem, user_id: int) -> dict | None:
    """Одна строка нагрузки для исполнителя (или пустая, если нет активных задач)."""
    for row in build_assignee_workload(subsystem):
        if row["user_id"] == user_id:
            return row
    user = User.objects.filter(pk=user_id).first()
    if not user:
        return None
    row = _empty_row(user.get_full_name() or user.username)
    row["user_id"] = user_id
    row["total_overdue"] = 0
    return row


def export_workload_xlsx(subsystem):
    from django.http import HttpResponse

    from delayu.services.uzhv_export import rows_to_xlsx_bytes

    rows = assignee_workload_csv_rows(subsystem)
    stamp = timezone.now().strftime("%Y%m%d")
    content = rows_to_xlsx_bytes(rows, sheet_title="Нагрузка")
    resp = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    resp["Content-Disposition"] = f'attachment; filename="uzhv_workload_{stamp}.xlsx"'
    return resp


def assignee_workload_csv_rows(subsystem) -> list[list]:
    rows = [
        [
            "Исполнитель",
            "Дела в работе",
            "Обращения в работе",
            "Проср. обращения",
            "Проср. предписания",
            "Проср. межвед.",
            "Итого просрочено",
        ]
    ]
    for item in build_assignee_workload(subsystem):
        rows.append(
            [
                item["name"],
                item["cases_open"],
                item["appeals_open"],
                item["appeals_overdue"],
                item["prescriptions_overdue"],
                item["interagency_overdue"],
                item["total_overdue"],
            ]
        )
    return rows
