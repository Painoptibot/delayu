"""Сделки воронки LED SALES и зеркало стадии на карточке заказчика."""
from __future__ import annotations

from delayu.models_service import ServiceCustomer, ServiceDeal


def next_deal_number(subsystem) -> str:
    seq = 0
    numbers = ServiceDeal.objects.filter(subsystem=subsystem).values_list("number", flat=True)
    for value in numbers:
        tail = str(value).rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"DL-{seq + 1:04d}"


def mirror_customer(deal: ServiceDeal) -> None:
    customer = deal.customer
    if customer.stage == deal.stage:
        return
    customer.stage = deal.stage
    customer.save(update_fields=["stage", "updated_at"])


def create_deal(*, customer: ServiceCustomer, title: str, stage: str | None = None, **extra) -> ServiceDeal:
    deal = ServiceDeal(
        subsystem=customer.subsystem,
        customer=customer,
        number=next_deal_number(customer.subsystem),
        title=title or customer.display_name,
        stage=stage or customer.stage or ServiceCustomer.Stage.NEW_LEAD,
        city=extra.pop("city", customer.city),
        state=extra.pop("state", customer.state),
        **extra,
    )
    if deal.stage == ServiceCustomer.Stage.WON:
        deal.status = ServiceDeal.Status.WON
    deal.save()
    mirror_customer(deal)
    from delayu.services.service_automation import run_workflows

    run_workflows(deal, "deal_created")
    return deal


def ensure_deal(customer: ServiceCustomer) -> ServiceDeal:
    deal = customer.deals.order_by("-updated_at").first()
    if deal is not None:
        return deal
    return create_deal(
        customer=customer,
        title=customer.display_name,
        stage=customer.stage,
        source="staff",
    )


def move_deal(deal: ServiceDeal, stage: str, *, actor: str = "система") -> ServiceDeal:
    previous = deal.stage
    previous_status = deal.status
    if stage == "lost":
        deal.status = ServiceDeal.Status.LOST
    else:
        deal.stage = stage
        deal.status = (
            ServiceDeal.Status.WON
            if stage == ServiceCustomer.Stage.WON
            else ServiceDeal.Status.OPEN
        )
    changed = deal.stage != previous or deal.status != previous_status
    deal.save()
    mirror_customer(deal)
    if changed:
        from delayu.services.service_process import write_audit

        write_audit(
            deal,
            customer=deal.customer,
            actor=actor,
            action="стадия",
            detail=f"{previous} → {deal.stage if stage != 'lost' else 'lost'}",
        )
    if stage != "lost" and stage != previous:
        from delayu.services.service_automation import run_workflows

        run_workflows(deal, "stage_changed")
    return deal


def push_customer_stage(customer: ServiceCustomer) -> ServiceDeal:
    """Стадия в карточке заказчика двигает последнюю живую сделку."""
    deal = customer.deals.exclude(status=ServiceDeal.Status.LOST).order_by("-updated_at").first()
    if deal is None:
        return ensure_deal(customer)
    if deal.stage != customer.stage:
        return move_deal(deal, customer.stage)
    return deal
