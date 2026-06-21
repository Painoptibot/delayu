"""PY-05 — пересчёт очереди учётных дел (ТЗ п. 489)."""
from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from delayu.models_uzhv import HousingQueueCase

# Меньше — выше приоритет в очереди
CATEGORY_PRIORITY: dict[str, int] = {
    HousingQueueCase.Category.ORPHAN: 0,
    HousingQueueCase.Category.VETERAN: 1,
    HousingQueueCase.Category.LOW_INCOME: 2,
    HousingQueueCase.Category.YOUNG_FAMILY: 3,
    HousingQueueCase.Category.GENERAL: 4,
}

QUEUE_STATUSES = frozenset(
    {
        HousingQueueCase.Status.REGISTERED,
        HousingQueueCase.Status.QUEUED,
    }
)

# Реестры по ТЗ п. 271–274
REGISTRY_MUNICIPAL_CATEGORIES = frozenset(
    {
        HousingQueueCase.Category.GENERAL,
        HousingQueueCase.Category.LOW_INCOME,
        HousingQueueCase.Category.YOUNG_FAMILY,
    }
)
REGISTRY_SPECIAL_CATEGORIES = frozenset(
    {
        HousingQueueCase.Category.ORPHAN,
        HousingQueueCase.Category.VETERAN,
    }
)


@dataclass
class QueueRecalcResult:
    updated: int = 0
    total: int = 0
    changes: list[str] = field(default_factory=list)


def _sort_key(case: HousingQueueCase) -> tuple:
    return (
        CATEGORY_PRIORITY.get(case.category, 99),
        case.registered_at,
        case.pk,
    )


@transaction.atomic
def recalculate_housing_queue(subsystem, *, dry_run: bool = False) -> QueueRecalcResult:
    """
    Начисление очереди: льготная категория → дата постановки на учёт → id.
    Дела со статусами «на учёте» / «в очереди» получают queue_position 1…N.
    """
    result = QueueRecalcResult()
    cases = list(
        HousingQueueCase.objects.filter(subsystem=subsystem, status__in=QUEUE_STATUSES).select_related(
            "citizen"
        )
    )
    result.total = len(cases)
    ordered = sorted(cases, key=_sort_key)

    inactive = HousingQueueCase.objects.filter(subsystem=subsystem).exclude(
        status__in=QUEUE_STATUSES
    ).exclude(queue_position__isnull=True)
    for case in inactive:
        label = f"{case.case_number} ({case.citizen.full_name})"
        result.changes.append(f"{label}: position {case.queue_position}->— (не в очереди)")
        if not dry_run:
            case.queue_position = None
            case.save(update_fields=["queue_position", "updated_at"])
        result.updated += 1

    for position, case in enumerate(ordered, start=1):
        updates: list[str] = []
        if case.queue_position != position:
            updates.append(f"position {case.queue_position}->{position}")
        if case.status == HousingQueueCase.Status.REGISTERED:
            updates.append("status->queued")
        if not updates:
            continue
        label = f"{case.case_number} ({case.citizen.full_name})"
        result.changes.append(f"{label}: {', '.join(updates)}")
        if not dry_run:
            case.queue_position = position
            case.status = HousingQueueCase.Status.QUEUED
            case.save(update_fields=["queue_position", "status", "updated_at"])
        result.updated += 1

    return result
