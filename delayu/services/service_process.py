"""Плейбук вида работ: одна карточка, общие стадии, очередь и след решений."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Sum
from django.utils import timezone

from delayu.models_service import (
    ServiceAudit,
    ServiceContact,
    ServiceCrewLine,
    ServiceCustomer,
    ServiceDeal,
    ServiceJobType,
    ServiceObject,
    ServiceObjectDeal,
    ServicePlaybook,
    ServiceReason,
    ServiceTask,
    ServiceVisit,
)
from delayu.services.service_automation import province_code
from delayu.services.service_dialogue import ServiceFlowError

UNIVERSAL = {
    "new_lead": "Вход",
    "contacted": "Вход",
    "replied": "Вход",
    "qualified": "Квалификация",
    "meeting": "Квалификация",
    "proposal": "Предложение",
    "active": "Обязательство",
    "invoice": "Обязательство",
    "setup": "Исполнение",
    "won": "Закрытие",
}

_CODE = re.compile(r"^[a-z0-9_-]{2,16}$")

_SEED_TYPES = (
    ("sale", "Продажа экрана", "0.72", "85.00", "40.00"),
    ("rental", "Аренда на событие", "0.72", "75.00", "35.00"),
    ("streaming", "Трансляция", "0.72", "90.00", "45.00"),
    ("stage", "Сцена", "0.80", "80.00", "50.00"),
    ("truss", "Фермы", "0.80", "80.00", "50.00"),
)

_LOST = ("Цена", "Срок", "Конкурент", "Нет бюджета")
_PAUSE = ("Ждём заказчика", "Ждём оборудование", "Сезон")


def _sale_rules() -> dict:
    return {
        "qualified": [
            {"field": "decision_maker", "equals": "yes", "gap": "не подтверждено лицо, которое принимает решение"},
            {"field": "screen_over_30", "equals": "yes", "gap": "экран не больше 30 кв. футов"},
            {"field": "state", "in": ["AB", "ON", "QC"], "gap": "провинция продажи не AB, ON или QC"},
        ],
        "proposal": [{"field": "value", "filled": True, "gap": "нет суммы предложения"}],
    }


def _rental_rules() -> dict:
    return {
        "qualified": [
            {"field": "guests_over_200", "equals": "yes", "gap": "гостей не больше 200"},
            {"field": "state", "in": ["AB", "QC"], "gap": "провинция аренды не AB и не QC"},
        ],
        "proposal": [{"field": "event_on", "filled": True, "gap": "нет даты события"}],
    }


def _place_rules() -> dict:
    return {"qualified": [{"field": "state", "filled": True, "gap": "нет провинции"}]}


def _steps(code: str) -> str:
    if code == "sale":
        return "Каталог на следующий день. Церковное письмо через два дня, если проект церковный. SMS по провинции."
    if code == "rental":
        return "Каталог аренды и дожим по провинции. Дата события обязательна до предложения."
    return "Первое касание, квалификация по провинции, предложение, счёт, выезд."


def _messages(code: str) -> dict:
    label = next((title for key, title, *_rest in _SEED_TYPES if key == code), code)
    return {
        "qualified": f"Your {label} project is qualified. We will send the next step in English.",
        "proposal": f"Your {label} proposal is ready. Reply if the size or the date should change.",
        "invoice": "Your invoice is ready. Payment keeps the same project card.",
        "setup": "Equipment setup is scheduled. The crew plan is on the same card.",
        "won": "The project is complete. This card stays the place for the next job.",
    }


def _gates(code: str) -> dict:
    if code == "sale":
        return _sale_rules()
    if code == "rental":
        return _rental_rules()
    return _place_rules()


def ensure_process(subsystem):
    titles = {code: title for code, title, *_rest in _SEED_TYPES}
    for code, title, mile, hour, crew in _SEED_TYPES:
        ServiceJobType.objects.get_or_create(
            subsystem=subsystem, code=code, defaults={"title": title}
        )
        ServicePlaybook.objects.get_or_create(
            subsystem=subsystem,
            job_type=code,
            defaults={
                "name": title,
                "mile_rate": Decimal(mile),
                "hour_rate": Decimal(hour),
                "crew_rate": Decimal(crew),
                "gates": _gates(code),
                "messages": _messages(code),
                "steps": _steps(code),
            },
        )
    for title in _LOST:
        ServiceReason.objects.get_or_create(
            subsystem=subsystem, kind=ServiceReason.Kind.LOST, title=title
        )
    for title in _PAUSE:
        ServiceReason.objects.get_or_create(
            subsystem=subsystem, kind=ServiceReason.Kind.PAUSE, title=title
        )
    from delayu.services.service_follow import ensure_follow

    ensure_follow(subsystem)
    return titles


def add_job_type(subsystem, code: str, title: str) -> ServicePlaybook:
    code = (code or "").strip().lower()
    title = (title or "").strip()
    if not _CODE.match(code):
        raise ServiceFlowError("Код вида работ: латиница, цифры, дефис, от 2 до 16 знаков.")
    if not title:
        raise ServiceFlowError("Нужно название вида работ.")
    ServiceJobType.objects.get_or_create(subsystem=subsystem, code=code, defaults={"title": title})
    book, _created = ServicePlaybook.objects.get_or_create(
        subsystem=subsystem,
        job_type=code,
        defaults={
            "name": title,
            "mile_rate": Decimal("0.72"),
            "hour_rate": Decimal("80.00"),
            "crew_rate": Decimal("40.00"),
            "gates": _place_rules(),
            "messages": _messages("streaming"),
            "steps": _steps(code),
        },
    )
    return book


def playbook_for(deal: ServiceDeal) -> ServicePlaybook | None:
    return ServicePlaybook.objects.filter(
        subsystem_id=deal.subsystem_id, job_type=deal.job_type
    ).first()


def universal_stage(stage: str) -> str:
    if stage == "lost":
        return "Закрытие"
    return UNIVERSAL.get(stage, "Вход")


def meeting_advances(deal: ServiceDeal) -> bool:
    book = playbook_for(deal)
    if book is None:
        return True
    return book.meeting_advances


def stage_text(deal: ServiceDeal) -> str:
    book = playbook_for(deal)
    if book is not None:
        text = (book.messages or {}).get(deal.stage) or ""
        if text:
            return text
    return f"Update: the project is at {deal.get_stage_display()}."


def gaps_for(deal: ServiceDeal, stage: str) -> list[str]:
    book = playbook_for(deal)
    if book is None:
        return []
    gaps = []
    for rule in (book.gates or {}).get(stage) or []:
        value = getattr(deal, rule.get("field") or "", None)
        if rule.get("equals") and str(value or "") != rule["equals"]:
            gaps.append(rule.get("gap") or rule["field"])
        elif rule.get("in"):
            if province_code(str(value or "")) not in set(rule["in"]):
                gaps.append(rule.get("gap") or rule["field"])
        elif rule.get("filled") and (value is None or value == ""):
            gaps.append(rule.get("gap") or rule["field"])
    return gaps


def write_audit(deal: ServiceDeal | None, *, customer, actor: str, action: str, detail: str) -> None:
    ServiceAudit.objects.create(
        subsystem=customer.subsystem,
        customer=customer,
        deal=deal,
        actor=(actor or "система")[:128],
        action=action[:64],
        detail=(detail or "")[:255],
    )


def advance_deal(deal: ServiceDeal, stage: str, *, actor: str) -> ServiceDeal:
    from delayu.services.service_deals import move_deal

    ensure_process(deal.subsystem)
    if deal.paused and stage != "lost":
        raise ServiceFlowError("Дело на паузе. Сначала снимите паузу: срок SLA стоит.")
    if stage == "lost":
        if not (deal.lost_reason or "").strip():
            raise ServiceFlowError("Нужна причина проигрыша из справочника.")
        return move_deal(deal, "lost", actor=actor)
    from delayu.services.service_follow import after_advance, blockers

    gaps = gaps_for(deal, stage) + blockers(deal, stage)
    if gaps:
        raise ServiceFlowError("Плейбук не пускает: " + "; ".join(gaps))
    moved = move_deal(deal, stage, actor=actor)
    after_advance(moved, stage, actor=actor)
    return moved


def repeat_deal(deal: ServiceDeal, *, actor: str) -> ServiceDeal:
    from delayu.services.service_deals import create_deal

    fresh = create_deal(
        customer=deal.customer,
        title=f"{deal.title} повтор"[:255],
        stage=ServiceCustomer.Stage.NEW_LEAD,
        job_type=deal.job_type,
        source="repeat",
        city=deal.city,
        state=deal.state,
        venue=deal.venue,
        placement=deal.placement,
        width_ft=deal.width_ft,
        height_ft=deal.height_ft,
        value=deal.value,
    )
    from delayu.services.service_follow import bump_revision

    bump_revision(deal, fresh)
    write_audit(
        fresh,
        customer=deal.customer,
        actor=actor,
        action="повтор",
        detail=f"Из {deal.number}, редакция {fresh.revision}, карточка {deal.customer.number} та же",
    )
    return fresh


def pause_deal(deal: ServiceDeal, reason: str, *, actor: str) -> None:
    reason = (reason or "").strip()
    if not reason:
        raise ServiceFlowError("Нужна причина паузы. Пауза канала исходящие держит отдельно.")
    deal.paused = True
    deal.pause_reason = reason[:255]
    deal.save(update_fields=["paused", "pause_reason", "updated_at"])
    write_audit(deal, customer=deal.customer, actor=actor, action="пауза дела", detail=reason)


def resume_deal(deal: ServiceDeal, *, actor: str) -> None:
    deal.paused = False
    deal.pause_reason = ""
    deal.save(update_fields=["paused", "pause_reason", "updated_at"])
    write_audit(deal, customer=deal.customer, actor=actor, action="снята пауза", detail=deal.number)


def assign_owner(deal: ServiceDeal, owner: str, observers: str, *, actor: str) -> None:
    deal.owner_name = (owner or "").strip()[:128]
    deal.observers = (observers or "").strip()[:255]
    deal.save(update_fields=["owner_name", "observers", "updated_at"])
    write_audit(
        deal,
        customer=deal.customer,
        actor=actor,
        action="владелец",
        detail=f"{deal.owner_name or 'не назначен'}; наблюдатели: {deal.observers or '—'}",
    )


def add_contact(customer: ServiceCustomer, *, name: str, role_name: str, phone: str, email: str, decides: bool):
    name = (name or "").strip()
    if not name:
        raise ServiceFlowError("Нужно имя контакта. Организация остаётся на карточке.")
    return ServiceContact.objects.create(
        customer=customer,
        name=name[:255],
        role_name=(role_name or "")[:128],
        phone=(phone or "")[:32],
        email=(email or "").strip(),
        decides=decides,
    )


def link_site(deal: ServiceDeal, site: ServiceObject) -> None:
    if site.customer_id != deal.customer_id:
        raise ServiceFlowError("Площадка принадлежит другому заказчику.")
    ServiceObjectDeal.objects.get_or_create(site=site, deal=deal)


def _qty(value) -> Decimal:
    try:
        return Decimal(str(value or 0).replace(",", "."))
    except InvalidOperation as exc:
        raise ServiceFlowError("План и факт записываются числом.") from exc


def add_crew(deal: ServiceDeal, *, title: str, kind: str, planned, actual, unit: str, site=None, damaged=False) -> ServiceCrewLine:
    title = (title or "").strip()
    if not title:
        raise ServiceFlowError("Нужно название силы или техники.")
    return ServiceCrewLine.objects.create(
        subsystem=deal.subsystem,
        deal=deal,
        site=site,
        title=title[:128],
        kind=kind or ServiceCrewLine.Kind.PEOPLE,
        planned=_qty(planned),
        actual=_qty(actual),
        unit=(unit or "чел")[:32],
        damaged=bool(damaged),
    )


def post_playbook_message(deal: ServiceDeal, *, user) -> None:
    from delayu.services.service_dialogue import post_message
    from delayu.models_service import ServiceMessage

    post_message(
        customer=deal.customer,
        channel="sms",
        direction=ServiceMessage.Direction.OUT,
        author_kind=ServiceMessage.AuthorKind.AGENT,
        kind=ServiceMessage.Kind.STAGE,
        body=stage_text(deal),
        user=user,
    )


def chronology(customer: ServiceCustomer) -> list[dict]:
    rows = []
    for message in customer.messages.all():
        rows.append({"at": message.created_at, "kind": "сообщение", "text": message.body[:180]})
    for audit in customer.audits.all():
        rows.append({"at": audit.created_at, "kind": audit.action, "text": f"{audit.actor}: {audit.detail}"})
    for task in customer.tasks.all():
        rows.append({"at": task.created_at, "kind": "задача", "text": task.title})
    for note in customer.internal_notes.all():
        rows.append({"at": note.created_at, "kind": "заметка", "text": note.body})
    for invoice in customer.invoices.all():
        stamp = timezone.make_aware(datetime.combine(invoice.issued_on, datetime.min.time()))
        rows.append({"at": stamp, "kind": "счёт", "text": f"{invoice.number} C${invoice.amount}"})
    for visit in ServiceVisit.objects.filter(site__customer=customer):
        stamp = timezone.make_aware(datetime.combine(visit.departed_on, datetime.min.time()))
        rows.append({"at": stamp, "kind": "выезд", "text": f"{visit.distance_mi} миль · C${visit.total_cost}"})
    rows.sort(key=lambda row: row["at"], reverse=True)
    return rows[:40]


def sla_missed(subsystem):
    now = timezone.now()
    missed = []
    deals = ServiceDeal.objects.filter(
        subsystem=subsystem,
        status=ServiceDeal.Status.OPEN,
        paused=False,
        stage=ServiceCustomer.Stage.NEW_LEAD,
    )
    for deal in deals:
        book = playbook_for(deal)
        hours = book.sla_first_hours if book is not None else 1
        if deal.created_at <= now - timedelta(hours=hours):
            missed.append(deal)
    return missed


def queue_snapshot(subsystem, role: str) -> dict:
    ensure_process(subsystem)
    open_deals = ServiceDeal.objects.filter(subsystem=subsystem, status=ServiceDeal.Status.OPEN)
    snapshot = {
        "role": role,
        "unassigned": list(open_deals.filter(owner_name="", paused=False)),
        "paused": list(open_deals.filter(paused=True)),
        "overdue": list(
            ServiceTask.objects.filter(
                subsystem=subsystem, done=False, due_on__lt=timezone.localdate()
            ).select_related("customer")
        ),
        "sla": sla_missed(subsystem),
        "sites": list(ServiceObject.objects.filter(subsystem=subsystem).exclude(status=ServiceObject.Status.DONE)),
        "stale": [],
        "due": [],
    }
    from delayu.services.service_follow import digest, due_deals, stale_deals

    snapshot["stale"] = stale_deals(subsystem)
    snapshot["due"] = due_deals(subsystem)
    if role == "sales":
        snapshot["sites"] = []
    elif role == "dispatcher":
        snapshot["unassigned"] = []
        snapshot["sla"] = []
        snapshot["stale"] = []
        snapshot["due"] = []
        snapshot["overdue"] = [task for task in snapshot["overdue"] if task.kind == ServiceTask.Kind.VISIT]
    snapshot["digest"] = digest(subsystem, snapshot)
    return snapshot


def report_slices(subsystem) -> dict:
    deals = ServiceDeal.objects.filter(subsystem=subsystem).exclude(status=ServiceDeal.Status.LOST)
    titles = {row.code: row.title for row in subsystem.service_job_types.all()}
    by_type = []
    for code, _label in ServiceCustomer.JobType.choices:
        bucket = deals.filter(job_type=code)
        by_type.append(
            {
                "label": titles.get(code, _label),
                "count": bucket.count(),
                "value": bucket.aggregate(total=Sum("value"))["total"] or 0,
            }
        )
    extra_codes = (
        deals.exclude(job_type__in=[code for code, _label in ServiceCustomer.JobType.choices])
        .values_list("job_type", flat=True)
        .distinct()
    )
    for code in extra_codes:
        bucket = deals.filter(job_type=code)
        by_type.append(
            {
                "label": titles.get(code, code),
                "count": bucket.count(),
                "value": bucket.aggregate(total=Sum("value"))["total"] or 0,
            }
        )
    by_state = []
    for state in deals.exclude(state="").values_list("state", flat=True).distinct():
        bucket = deals.filter(state=state)
        by_state.append(
            {
                "label": state,
                "count": bucket.count(),
                "value": bucket.aggregate(total=Sum("value"))["total"] or 0,
            }
        )
    since = timezone.now() - timedelta(days=7)
    week = deals.filter(updated_at__gte=since)
    owners = []
    names = list(week.exclude(owner_name="").values_list("owner_name", flat=True).distinct())
    for name in names:
        bucket = week.filter(owner_name=name)
        owners.append({"label": name, "count": bucket.count(), "value": bucket.aggregate(total=Sum("value"))["total"] or 0})
    idle = week.filter(owner_name="").count()
    if idle:
        owners.append({"label": "Без владельца", "count": idle, "value": 0})
    from delayu.services.service_follow import forecast, scoreboard

    return {
        "by_type": by_type,
        "by_state": by_state,
        "owners": owners,
        "week_count": week.count(),
        "forecast": forecast(subsystem),
        "scoreboard": scoreboard(subsystem),
    }


def customer_process(customer: ServiceCustomer) -> dict:
    ensure_process(customer.subsystem)
    from delayu.services.service_follow import pack_follow

    packed = {
        "contacts": customer.contacts.all(),
        "pause_reasons": customer.subsystem.service_reasons.filter(kind=ServiceReason.Kind.PAUSE),
        "lost_reasons": customer.subsystem.service_reasons.filter(kind=ServiceReason.Kind.LOST),
        "story": chronology(customer),
        "crew_lines": ServiceCrewLine.objects.filter(deal__customer=customer),
        "universal": UNIVERSAL,
        "job_types": customer.subsystem.service_job_types.filter(active=True),
    }
    packed.update(pack_follow(customer))
    return packed
