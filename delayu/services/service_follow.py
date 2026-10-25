"""Вторая очередь сопровождения: чеклист, гарантия, маршрут, слияние, сводка."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from delayu.models_service import (
    ServiceChannel,
    ServiceChecklist,
    ServiceCheckMark,
    ServiceCustomer,
    ServiceDeal,
    ServiceGear,
    ServiceInvoice,
    ServiceNote,
    ServicePlaybook,
    ServiceRoute,
    ServiceTask,
)
from delayu.services.service_automation import province_code
from delayu.services.service_dialogue import ServiceFlowError
from delayu.services.service_field import customer_totals
from delayu.services.service_process import playbook_for, write_audit

_SALE_CHECKS = (
    ("qualified", "Решение записано"),
    ("qualified", "Размер записан"),
)
_RENTAL_CHECKS = (("proposal", "Дата события подтверждена"),)


def ensure_follow(subsystem):
    sale = ServicePlaybook.objects.filter(subsystem=subsystem, job_type="sale").first()
    if sale is not None and not sale.after_hours:
        sale.warranty_days = sale.warranty_days or 365
        sale.approval_amount = sale.approval_amount or Decimal("2500.00")
        sale.after_hours = "We are closed. The same card will get a reply on the next business morning."
        sale.save(update_fields=["warranty_days", "approval_amount", "after_hours"])
    rental = ServicePlaybook.objects.filter(subsystem=subsystem, job_type="rental").first()
    for book, rows in ((sale, _SALE_CHECKS), (rental, _RENTAL_CHECKS)):
        if book is None:
            continue
        for stage, title in rows:
            ServiceChecklist.objects.get_or_create(playbook=book, stage=stage, title=title)


def blockers(deal: ServiceDeal, stage: str) -> list[str]:
    book = playbook_for(deal)
    gaps = []
    if book is None:
        return gaps
    items = book.checks.filter(stage=stage)
    done_ids = set(
        ServiceCheckMark.objects.filter(deal=deal, item__in=items, done=True).values_list("item_id", flat=True)
    )
    for item in items:
        if item.pk not in done_ids:
            gaps.append(item.title)
    if stage == ServiceCustomer.Stage.SETUP and not deal.media_files.exists():
        gaps.append("до монтажа нужен файл этого дела в медиатеке")
    return gaps


def after_advance(deal: ServiceDeal, stage: str, *, actor: str) -> None:
    if stage != ServiceCustomer.Stage.WON:
        return
    book = playbook_for(deal)
    days = book.warranty_days if book is not None else 0
    if days:
        deal.warranty_on = timezone.localdate() + timedelta(days=days)
        deal.save(update_fields=["warranty_on", "updated_at"])
    title = "Вернуть экран" if deal.job_type == ServiceCustomer.JobType.RENTAL else "Закрыть дело с заказчиком"
    ServiceTask.objects.get_or_create(
        subsystem=deal.subsystem,
        customer=deal.customer,
        deal=deal,
        title=title,
        defaults={"kind": ServiceTask.Kind.FOLLOWUP, "due_on": timezone.localdate()},
    )
    write_audit(deal, customer=deal.customer, actor=actor, action="закрытие", detail=title)


def toggle_check(deal: ServiceDeal, item: ServiceChecklist) -> None:
    if item.playbook.job_type != deal.job_type or item.playbook.subsystem_id != deal.subsystem_id:
        raise ServiceFlowError("Пункт относится к другому плейбуку.")
    mark, _created = ServiceCheckMark.objects.get_or_create(deal=deal, item=item)
    mark.done = not mark.done
    mark.save(update_fields=["done"])


def set_next(deal: ServiceDeal, day, *, actor: str) -> None:
    deal.next_on = day
    deal.save(update_fields=["next_on", "updated_at"])
    write_audit(
        deal,
        customer=deal.customer,
        actor=actor,
        action="следующее действие",
        detail=str(day or "снято"),
    )


def add_note(deal: ServiceDeal, body: str, *, actor: str) -> None:
    body = (body or "").strip()
    if not body:
        raise ServiceFlowError("Нужен текст внутренней заметки. Заказчик её не видит.")
    ServiceNote.objects.create(customer=deal.customer, deal=deal, body=body[:255])
    write_audit(deal, customer=deal.customer, actor=actor, action="заметка", detail=body[:255])


def save_route(subsystem, *, job_type: str, province: str, owner_name: str) -> ServiceRoute:
    province = province_code(province)
    owner_name = (owner_name or "").strip()
    if not province or not owner_name:
        raise ServiceFlowError("Нужны провинция и владелец маршрута.")
    route, _created = ServiceRoute.objects.update_or_create(
        subsystem=subsystem,
        job_type=(job_type or "sale")[:16],
        province=province[:8],
        defaults={"owner_name": owner_name[:128]},
    )
    return route


def apply_route(deal: ServiceDeal, *, actor: str) -> ServiceDeal:
    route = ServiceRoute.objects.filter(
        subsystem=deal.subsystem,
        job_type=deal.job_type,
        province=province_code(deal.state),
    ).first()
    if route is None:
        raise ServiceFlowError("Маршрута для этой провинции и вида работ нет.")
    deal.owner_name = route.owner_name
    deal.save(update_fields=["owner_name", "updated_at"])
    write_audit(deal, customer=deal.customer, actor=actor, action="маршрут", detail=route.owner_name)
    return deal


def mark_deposit(invoice: ServiceInvoice) -> None:
    invoice.kind = "deposit" if invoice.kind != "deposit" else "final"
    invoice.save(update_fields=["kind"])


def add_gear(site, title: str, serial: str) -> ServiceGear:
    title = (title or "").strip()
    serial = (serial or "").strip()
    if not title or not serial:
        raise ServiceFlowError("Нужны название оборудования и серийный номер.")
    gear, _created = ServiceGear.objects.get_or_create(
        site=site, serial=serial[:64], defaults={"title": title[:128]}
    )
    return gear


def phone_key(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return digits[-10:]


def duplicate_customers(customer: ServiceCustomer):
    key = phone_key(customer.phone)
    if len(key) < 10:
        return []
    rows = []
    for other in ServiceCustomer.objects.filter(subsystem=customer.subsystem).exclude(pk=customer.pk):
        if phone_key(other.phone) == key:
            rows.append(other)
    return rows


def merge_customers(keeper: ServiceCustomer, other: ServiceCustomer, *, actor: str) -> None:
    if keeper.pk == other.pk:
        raise ServiceFlowError("Это та же карточка.")
    if keeper.subsystem_id != other.subsystem_id:
        raise ServiceFlowError("Карточка из другого контура.")
    other.deals.update(customer=keeper)
    other.contacts.update(customer=keeper)
    other.tasks.update(customer=keeper)
    other.messages.update(customer=keeper)
    other.sites.update(customer=keeper)
    other.invoices.update(customer=keeper)
    other.audits.update(customer=keeper)
    other.appointments.update(customer=keeper)
    other.internal_notes.update(customer=keeper)
    number = other.number
    other.delete()
    write_audit(None, customer=keeper, actor=actor, action="слияние", detail=f"Забрана карточка {number}")


def clone_playbook(book: ServicePlaybook, code: str, title: str) -> ServicePlaybook:
    from delayu.services.service_process import add_job_type

    add_job_type(book.subsystem, code, title)
    fresh = ServicePlaybook.objects.get(subsystem=book.subsystem, job_type=code.strip().lower())
    fresh.gates = book.gates
    fresh.messages = book.messages
    fresh.steps = book.steps
    fresh.mile_rate = book.mile_rate
    fresh.hour_rate = book.hour_rate
    fresh.crew_rate = book.crew_rate
    fresh.sla_first_hours = book.sla_first_hours
    fresh.sla_stage_hours = book.sla_stage_hours
    fresh.stale_days = book.stale_days
    fresh.warranty_days = book.warranty_days
    fresh.approval_amount = book.approval_amount
    fresh.after_hours = book.after_hours
    fresh.meeting_advances = book.meeting_advances
    fresh.save()
    for item in book.checks.all():
        ServiceChecklist.objects.get_or_create(playbook=fresh, stage=item.stage, title=item.title)
    return fresh


def _plain_number(value, default: str) -> str:
    text = default if value in (None, "") else str(value)
    return text.replace("\xa0", "").replace(" ", "").replace(",", ".").strip()


def save_norms(book: ServicePlaybook, *, stale_days: int, warranty_days: int, approval_amount, after_hours: str):
    try:
        book.stale_days = max(int(Decimal(_plain_number(stale_days, "7"))), 1)
        book.warranty_days = max(int(Decimal(_plain_number(warranty_days, "0"))), 0)
        book.approval_amount = Decimal(_plain_number(approval_amount, "0"))
    except (InvalidOperation, ValueError) as exc:
        raise ServiceFlowError("Нормы записываются числом. Сумму можно ввести как 2500.00 или 2500,00.") from exc
    book.after_hours = (after_hours or "")[:255]
    book.save(update_fields=["stale_days", "warranty_days", "approval_amount", "after_hours"])


def stale_deals(subsystem):
    now = timezone.now()
    rows = []
    deals = ServiceDeal.objects.filter(subsystem=subsystem, status=ServiceDeal.Status.OPEN, paused=False)
    for deal in deals:
        book = playbook_for(deal)
        days = book.stale_days if book is not None else 7
        if deal.updated_at <= now - timedelta(days=days):
            rows.append(deal)
    return rows


def due_deals(subsystem):
    return list(
        ServiceDeal.objects.filter(
            subsystem=subsystem,
            status=ServiceDeal.Status.OPEN,
            paused=False,
            next_on__lte=timezone.localdate(),
        )
    )


def escalate_overdue(subsystem) -> int:
    made = 0
    tasks = ServiceTask.objects.filter(
        subsystem=subsystem, done=False, due_on__lt=timezone.localdate()
    ).select_related("deal", "customer")
    for task in tasks:
        deal = task.deal
        if deal is None or not deal.observers:
            continue
        title = f"Эскалация: {task.title}"[:255]
        _, created = ServiceTask.objects.get_or_create(
            subsystem=subsystem,
            customer=task.customer,
            deal=deal,
            title=title,
            defaults={"kind": ServiceTask.Kind.FOLLOWUP, "note": deal.observers[:255], "due_on": timezone.localdate()},
        )
        if created:
            made += 1
    return made


def digest(subsystem, snapshot: dict) -> str:
    paused_channels = ServiceChannel.objects.filter(
        subsystem=subsystem, status=ServiceChannel.Status.PAUSED
    ).count()
    return (
        f"Неназначенных {len(snapshot['unassigned'])}, "
        f"SLA {len(snapshot['sla'])}, "
        f"пауза дел {len(snapshot['paused'])}, "
        f"каналов на паузе {paused_channels}, "
        f"без движения {len(snapshot['stale'])}, "
        f"к действию {len(snapshot['due'])}."
    )


def forecast(subsystem):
    deals = ServiceDeal.objects.filter(subsystem=subsystem, event_on__isnull=False).exclude(
        status=ServiceDeal.Status.LOST
    )
    rows = []
    for row in (
        deals.annotate(month=TruncMonth("event_on"))
        .values("month")
        .annotate(count=Count("id"), total=Sum("value"))
        .order_by("month")
    ):
        rows.append(
            {
                "label": row["month"].strftime("%Y-%m") if row["month"] else "—",
                "count": row["count"],
                "value": row["total"] or 0,
            }
        )
    return rows


def scoreboard(subsystem):
    since = timezone.now() - timedelta(days=7)
    won = ServiceDeal.objects.filter(
        subsystem=subsystem, status=ServiceDeal.Status.WON, updated_at__gte=since
    )
    rows = []
    for name in won.exclude(owner_name="").values_list("owner_name", flat=True).distinct():
        rows.append({"label": name, "count": won.filter(owner_name=name).count()})
    return rows


def approval_text(customer: ServiceCustomer) -> str:
    totals = customer_totals(customer)
    limit = Decimal("0")
    for deal in customer.deals.exclude(status=ServiceDeal.Status.LOST):
        book = playbook_for(deal)
        if book is not None and book.approval_amount > limit:
            limit = book.approval_amount
    if limit and totals["total"] > limit:
        return f"Затраты C${totals['total']} выше порога C${limit}. Нужно согласование."
    return ""


def bump_revision(source: ServiceDeal, fresh: ServiceDeal) -> None:
    fresh.revision = (source.revision or 1) + 1
    fresh.save(update_fields=["revision"])


def pack_follow(customer: ServiceCustomer) -> dict:
    deal_ids = list(customer.deals.values_list("pk", flat=True))
    checks = []
    for deal in customer.deals.all():
        book = playbook_for(deal)
        if book is None:
            continue
        done = {
            mark.item_id: mark.done
            for mark in ServiceCheckMark.objects.filter(deal=deal)
        }
        for item in book.checks.all():
            checks.append({"deal": deal, "item": item, "done": done.get(item.pk, False)})
    return {
        "checks": checks,
        "notes": customer.internal_notes.all()[:12],
        "duplicates": duplicate_customers(customer),
        "gears": ServiceGear.objects.filter(site__customer=customer),
        "approval": approval_text(customer),
        "others": ServiceCustomer.objects.filter(subsystem=customer.subsystem).exclude(pk=customer.pk),
        "deal_ids": deal_ids,
    }
