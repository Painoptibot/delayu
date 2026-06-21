"""PY-07 — payload уведомлений для последующей отправки (I-06 заготовка)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from django.utils import timezone

from delayu.models_uzhv import (
    HousingAppeal,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
)


@dataclass
class NotifyPayloadResult:
    count: int = 0
    files: list[str] = field(default_factory=list)


def _write_payload(out_dir: Path, name: str, payload: dict) -> str:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def build_notify_payloads(subsystem, out_dir: Path, *, days_ahead: int = 3) -> NotifyPayloadResult:
    """
    Формирует JSON-файлы событий: просроченные/скорые обращения, предписания, межвед. запросы.
    """
    result = NotifyPayloadResult()
    now = timezone.now()
    today = now.date()
    horizon = today + timedelta(days=days_ahead)
    ts = now.strftime("%Y%m%d_%H%M%S")

    closed = {HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED}
    appeals = HousingAppeal.objects.filter(subsystem=subsystem).exclude(status__in=closed)
    for appeal in appeals.filter(due_date__lte=horizon).select_related("citizen", "housing_case")[:200]:
        payload = {
            "event": "appeal.deadline",
            "channel": "epgu_stub",
            "subsystem_code": subsystem.code,
            "appeal_id": appeal.pk,
            "appeal_number": appeal.appeal_number,
            "due_date": appeal.due_date.isoformat(),
            "overdue": appeal.due_date < today,
            "citizen_name": appeal.citizen.full_name if appeal.citizen_id else "",
            "subject": appeal.subject[:500],
            "message": (
                f"Обращение {appeal.appeal_number}: срок исполнения {appeal.due_date:%d.%m.%Y}"
            ),
        }
        fname = f"appeal_{appeal.pk}_{ts}.json"
        result.files.append(_write_payload(out_dir, fname, payload))
        result.count += 1

    for rx in HousingInteragencyRequest.objects.filter(subsystem=subsystem).exclude(
        status__in=(HousingInteragencyRequest.Status.ANSWERED, HousingInteragencyRequest.Status.CANCELLED)
    ).filter(due_date__lte=horizon)[:100]:
        payload = {
            "event": "interagency.deadline",
            "channel": "epgu_stub",
            "subsystem_code": subsystem.code,
            "request_id": rx.pk,
            "request_number": rx.request_number,
            "due_date": rx.due_date.isoformat(),
            "recipient": rx.recipient_name,
            "message": f"Ожидается ответ по запросу {rx.request_number}",
        }
        fname = f"interagency_{rx.pk}_{ts}.json"
        result.files.append(_write_payload(out_dir, fname, payload))
        result.count += 1

    for pr in HousingPrescription.objects.filter(inspection__subsystem=subsystem).exclude(
        status__in=(HousingPrescription.Status.FULFILLED, HousingPrescription.Status.CANCELLED)
    ).filter(due_date__lte=horizon)[:100]:
        payload = {
            "event": "prescription.deadline",
            "channel": "epgu_stub",
            "subsystem_code": subsystem.code,
            "prescription_id": pr.pk,
            "due_date": pr.due_date.isoformat(),
            "message": f"Срок исполнения предписания {pr.prescription_number}",
        }
        fname = f"prescription_{pr.pk}_{ts}.json"
        result.files.append(_write_payload(out_dir, fname, payload))
        result.count += 1

    for case in HousingQueueCase.objects.filter(
        subsystem=subsystem,
        status=HousingQueueCase.Status.QUEUED,
        low_income_eligible=True,
        queue_position__lte=10,
    ).select_related("citizen")[:50]:
        payload = {
            "event": "case.queue_ready",
            "channel": "epgu_stub",
            "subsystem_code": subsystem.code,
            "case_id": case.pk,
            "case_number": case.case_number,
            "queue_position": case.queue_position,
            "citizen_name": case.citizen.full_name,
            "message": f"Дело {case.case_number} в очереди на позиции {case.queue_position}",
        }
        fname = f"case_{case.pk}_{ts}.json"
        result.files.append(_write_payload(out_dir, fname, payload))
        result.count += 1

    return result
