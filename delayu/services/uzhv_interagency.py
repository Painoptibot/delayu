"""Межведомственные запросы УЖВ: нумерация и статусы."""
from __future__ import annotations

import re

from django.db import transaction
from django.utils import timezone

from delayu.models_uzhv import HousingInteragencyRequest


@transaction.atomic
def next_interagency_number(subsystem) -> str:
    year = timezone.now().year
    base = f"МВ-{year}-"
    last = (
        HousingInteragencyRequest.objects.select_for_update()
        .filter(subsystem=subsystem, request_number__startswith=base)
        .order_by("-request_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.request_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


def sync_overdue_interagency(subsystem) -> int:
    today = timezone.now().date()
    qs = HousingInteragencyRequest.objects.filter(
        subsystem=subsystem,
        due_date__lt=today,
    ).exclude(
        status__in=[
            HousingInteragencyRequest.Status.ANSWERED,
            HousingInteragencyRequest.Status.CANCELLED,
            HousingInteragencyRequest.Status.OVERDUE,
        ]
    )
    return qs.update(status=HousingInteragencyRequest.Status.OVERDUE)
