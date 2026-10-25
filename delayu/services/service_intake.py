"""Заявки с сайта: квота на покупку и квота на аренду открывают сделку New Lead."""
from __future__ import annotations

from delayu.models_service import ServiceCustomer, ServiceDeal
from delayu.services.service_automation import run_workflows
from delayu.services.service_deals import create_deal

SALE_SOURCE = "Website — SALES Quote"
RENTAL_SOURCE = "Website — RENTAL Quote"


def _next_customer_number(subsystem) -> str:
    seq = 0
    numbers = ServiceCustomer.objects.filter(subsystem=subsystem).values_list("number", flat=True)
    for value in numbers:
        tail = str(value).rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"ZK-{seq + 1:04d}"


def _split_location(location: str) -> tuple[str, str]:
    parts = [part.strip() for part in (location or "").split(",") if part.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return parts[0] if parts else "", ""


def open_quote(*, subsystem, kind: str, data: dict, catalog: bool = False):
    """Создаёт заказчика и сделку, затем квалификацию и дожим."""
    city, state = _split_location(data.get("location") or "")
    if data.get("city"):
        city = data["city"]
    if data.get("state"):
        state = data["state"]
    sale = kind == "sale"
    customer = ServiceCustomer.objects.create(
        subsystem=subsystem,
        number=_next_customer_number(subsystem),
        display_name=data["display_name"],
        phone=data.get("phone") or "",
        email=data.get("email") or "",
        city=city,
        state=state,
        stage=ServiceCustomer.Stage.NEW_LEAD,
        tags="buy" if sale else "rental",
        notes=data.get("message") or "",
    )
    deal = create_deal(
        customer=customer,
        title=customer.display_name,
        stage=ServiceCustomer.Stage.NEW_LEAD,
        job_type=ServiceCustomer.JobType.SALE if sale else ServiceCustomer.JobType.RENTAL,
        source=SALE_SOURCE if sale else RENTAL_SOURCE,
        city=city,
        state=state,
        venue=data.get("location") or city,
        timeline=data.get("timeline") or "",
        event_on=data.get("event_on"),
        decision_maker=data.get("decision_maker") or ServiceDeal.Answer.UNKNOWN,
        screen_over_30=data.get("screen_over_30") or ServiceDeal.Answer.UNKNOWN,
        guests_over_200=data.get("guests_over_200") or ServiceDeal.Answer.UNKNOWN,
        church_project=data.get("church_project") or ServiceDeal.Answer.UNKNOWN,
    )
    run_workflows(deal, "deal_ready", catalog=catalog)
    return customer, deal


def open_form_lead(*, subsystem, form_name: str, display_name: str, phone: str, email: str, message: str):
    """Заявка из формы аккаунта открывает заказчика и сделку New Lead."""
    lowered = (form_name or "").lower()
    rental = "rental" in lowered or "rent" in lowered
    catalog = "catalog" in lowered
    church = "church" in lowered
    customer, deal = open_quote(
        subsystem=subsystem,
        kind="rental" if rental else "sale",
        data={
            "display_name": display_name,
            "phone": phone,
            "email": email,
            "message": message,
            "church_project": ServiceDeal.Answer.YES if church else ServiceDeal.Answer.UNKNOWN,
        },
        catalog=catalog,
    )
    deal.source = form_name[:128]
    deal.save(update_fields=["source", "updated_at"])
    return customer, deal
