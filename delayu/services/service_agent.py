"""ИИ-агент карточки: отвечает по фактам и сообщает об этапе или оплате.

Текст заказчику — на английском: контур ведёт проекты в США.
"""
from __future__ import annotations

from delayu.models_service import ServiceCustomer, ServiceMessage, money
from delayu.services.service_dialogue import post_message
from delayu.services.service_field import customer_totals

STAGE_EN = {
    "new_lead": "new lead",
    "contacted": "contacted",
    "replied": "replied",
    "qualified": "qualified",
    "meeting": "meeting scheduled",
    "proposal": "proposal sent",
    "active": "active deal",
    "invoice": "invoice sent",
    "setup": "equipment setup",
    "won": "won",
}
WORK_EN = {
    "proposal": "proposal",
    "setup": "setup on site",
    "complete": "complete",
}
PAYMENT_EN = {
    "none": "no invoice yet",
    "invoiced": "invoice sent",
    "partial": "partially paid",
    "paid": "paid",
}
JOB_EN = {
    "sale": "LED screen sale",
    "rental": "event rental",
    "streaming": "live streaming",
    "stage": "stage rental",
    "truss": "truss rental",
}


def _job_line(site) -> str:
    place = ", ".join(part for part in (site.city, site.state) if part)
    where = f" in {place}" if place else ""
    size = ""
    if site.width_ft and site.height_ft:
        size = f", {site.width_ft:g} x {site.height_ft:g} ft"
    when = f", date {site.event_on}" if site.event_on else ""
    return (
        f"{site.title}{where}: {JOB_EN.get(site.job_type, site.job_type)}, "
        f"{site.get_placement_display()}{size}{when}, {WORK_EN.get(site.stage, site.stage)}."
    )


def compose_stage(customer: ServiceCustomer) -> str:
    lines = [
        f"{customer.display_name}, your project is at {STAGE_EN.get(customer.stage, customer.stage)}.",
    ]
    sites = list(customer.sites.all())
    if sites:
        lines.extend(_job_line(site) for site in sites)
    else:
        lines.append("No venue is on this card yet.")
    return " ".join(lines)


def compose_payment(customer: ServiceCustomer) -> str:
    state = PAYMENT_EN.get(customer.payment_state, customer.payment_state)
    if customer.invoice_amount is None:
        amount = "the invoice amount is not on the card yet"
    else:
        amount = f"the invoice is C${money(customer.invoice_amount)}"
    spent = customer_totals(customer)["total"]
    return (
        f"{customer.display_name}, payment: {state}, {amount}. "
        f"Trip and crew costs recorded on the jobs: C${spent}."
    )


def answer_question(customer: ServiceCustomer, question: str) -> str:
    """Ответ только из карточки. Сумму, которой нет в учёте, агент не называет."""
    text = (question or "").lower().replace("ё", "е")
    if any(word in text for word in ("оплат", "счет", "счёт", "деньг", "pay", "invoice", "bill")):
        return compose_payment(customer)
    if any(
        word in text
        for word in ("этап", "стад", "работ", "статус", "объект", "stage", "status", "install", "screen", "venue")
    ):
        return compose_stage(customer)
    if any(word in text for word in ("выезд", "затрат", "километр", "силы", "mile", "cost", "crew", "trip")):
        totals = customer_totals(customer)
        return (
            f"For {customer.display_name}: mileage C${totals['travel']}, "
            f"crew hours C${totals['labor']}, other trip costs C${totals['other']}, "
            f"people and gear C${totals['resources']}. Together C${totals['total']}."
        )
    bits = [f"{customer.display_name}."]
    if customer.company:
        bits.append(f"Company: {customer.company}.")
    if customer.phone:
        bits.append(f"Phone: {customer.phone}.")
    if customer.email:
        bits.append(f"Email: {customer.email}.")
    if customer.city or customer.state:
        bits.append(f"Location: {', '.join(part for part in (customer.city, customer.state) if part)}.")
    bits.append(f"Stage: {STAGE_EN.get(customer.stage, customer.stage)}.")
    bits.append(f"Payment: {PAYMENT_EN.get(customer.payment_state, customer.payment_state)}.")
    bits.append("Ask about the install stage, the invoice, or trip costs.")
    return " ".join(bits)


def ask_and_record(*, customer, channel: str, question: str, user=None) -> ServiceMessage:
    post_message(
        customer=customer,
        channel=channel,
        direction=ServiceMessage.Direction.IN,
        author_kind=ServiceMessage.AuthorKind.CUSTOMER,
        body=question,
        kind=ServiceMessage.Kind.DIALOGUE,
        user=user,
    )
    return post_message(
        customer=customer,
        channel=channel,
        direction=ServiceMessage.Direction.OUT,
        author_kind=ServiceMessage.AuthorKind.AGENT,
        body=answer_question(customer, question),
        kind=ServiceMessage.Kind.ANSWER,
        user=user,
    )


def queue_notice(*, customer, channel: str, kind: str, scheduled_for=None, user=None) -> ServiceMessage:
    if kind == ServiceMessage.Kind.PAYMENT:
        body = compose_payment(customer)
    else:
        kind = ServiceMessage.Kind.STAGE
        body = compose_stage(customer)
    return post_message(
        customer=customer,
        channel=channel,
        direction=ServiceMessage.Direction.OUT,
        author_kind=ServiceMessage.AuthorKind.AGENT,
        body=body,
        kind=kind,
        scheduled_for=scheduled_for,
        user=user,
    )
