"""Сервисы АИС УЖВ: нумерация, обращения, SLA."""
from __future__ import annotations

import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from delayu.models import Correspondence, CorrespondenceEvent
from delayu.models_uzhv import HousingAppeal, HousingContract, HousingInspection, HousingQueueCase
from delayu.services.correspondence import log_event, register_correspondence


@transaction.atomic
def next_case_number(subsystem) -> str:
    year = timezone.now().year
    base = f"УЖВ-{year}-"
    last = (
        HousingQueueCase.objects.select_for_update()
        .filter(subsystem=subsystem, case_number__startswith=base)
        .order_by("-case_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.case_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


@transaction.atomic
def next_appeal_number(subsystem) -> str:
    year = timezone.now().year
    base = f"ОБР-{year}-"
    last = (
        HousingAppeal.objects.select_for_update()
        .filter(subsystem=subsystem, appeal_number__startswith=base)
        .order_by("-appeal_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.appeal_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:04d}"


def appeal_due_date(received_at):
    return received_at + timedelta(days=HousingAppeal.SLA_DAYS)


@transaction.atomic
def register_housing_appeal(
    *,
    subsystem,
    user,
    subject,
    body="",
    citizen=None,
    housing_case=None,
    assignee=None,
    received_at=None,
):
    """Регистрация обращения + входящая корреспонденция (M24)."""
    received_at = received_at or timezone.now().date()
    due = appeal_due_date(received_at)
    counterparty = citizen.full_name if citizen else ""
    corr = register_correspondence(
        subsystem=subsystem,
        user=user,
        direction=Correspondence.Direction.IN,
        subject=subject[:500],
        counterparty=counterparty,
        assignee=assignee,
        status=Correspondence.Status.IN_WORK,
    )
    appeal = HousingAppeal.objects.create(
        subsystem=subsystem,
        appeal_number=next_appeal_number(subsystem),
        received_at=received_at,
        due_date=due,
        citizen=citizen,
        housing_case=housing_case,
        correspondence=corr,
        subject=subject,
        body=body,
        status=HousingAppeal.Status.IN_WORK,
        assignee=assignee or user,
        created_by=user,
    )
    log_event(
        corr,
        CorrespondenceEvent.EventType.REGISTERED,
        f"Обращение {appeal.appeal_number}, срок ответа до {due:%d.%m.%Y}",
        actor=user,
    )
    from delayu.services.uzhv_appeal_status import record_appeal_status_change

    record_appeal_status_change(
        appeal,
        old_status="",
        new_status=appeal.status,
        user=user,
        comment="Регистрация обращения",
    )
    return appeal


@transaction.atomic
def next_inspection_number(subsystem) -> str:
    year = timezone.now().year
    base = f"ПР-{year}-"
    last = (
        HousingInspection.objects.select_for_update()
        .filter(subsystem=subsystem, inspection_number__startswith=base)
        .order_by("-inspection_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.inspection_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


@transaction.atomic
def next_inspection_plan_number(subsystem) -> str:
    year = timezone.now().year
    base = f"ПЛ-{year}-"
    from delayu.models_uzhv import HousingInspectionPlan

    last = (
        HousingInspectionPlan.objects.select_for_update()
        .filter(subsystem=subsystem, plan_number__startswith=base)
        .order_by("-plan_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.plan_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


@transaction.atomic
def next_inspection_order_number(subsystem) -> str:
    year = timezone.now().year
    base = f"ПВ-{year}-"
    from delayu.models_uzhv import HousingInspectionOrder

    last = (
        HousingInspectionOrder.objects.select_for_update()
        .filter(subsystem=subsystem, order_number__startswith=base)
        .order_by("-order_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.order_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


@transaction.atomic
def next_contract_number(subsystem) -> str:
    year = timezone.now().year
    base = f"ДН-{year}-"
    last = (
        HousingContract.objects.select_for_update()
        .filter(subsystem=subsystem, contract_number__startswith=base)
        .order_by("-contract_number")
        .first()
    )
    n = 1
    if last:
        m = re.search(r"-(\d+)$", last.contract_number)
        if m:
            n = int(m.group(1)) + 1
    return f"{base}{n:03d}"


def filter_appeals(subsystem, *, params=None):
    from django.db.models import Q

    params = params or {}
    qs = HousingAppeal.objects.filter(subsystem=subsystem).select_related(
        "citizen", "assignee", "housing_case", "correspondence"
    )
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(appeal_number__icontains=q)
            | Q(subject__icontains=q)
            | Q(citizen__last_name__icontains=q)
            | Q(citizen__first_name__icontains=q)
        )
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    if params.get("overdue") == "1":
        today = timezone.now().date()
        qs = qs.filter(due_date__lt=today).exclude(
            status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
        )
    assignee = (params.get("assignee") or "").strip()
    if assignee.isdigit():
        qs = qs.filter(assignee_id=int(assignee))
    return qs.order_by("due_date", "-received_at")
