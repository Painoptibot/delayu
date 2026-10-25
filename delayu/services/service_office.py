"""Календари, воронки сайта, рассылки, реклама, счета и медиатека."""
from __future__ import annotations

from django.utils import timezone

from delayu.models_service import (
    ServiceAd,
    ServiceCalendar,
    ServiceCustomer,
    ServiceDeal,
    ServiceFunnel,
    ServiceInvoice,
    ServiceMessage,
)
from delayu.services.service_deals import create_deal, move_deal

CALENDARS = (
    ("Online LED Screen Project Discussion", ServiceCalendar.Kind.MEETING, "Общий"),
    ("LED Screen Project Consultation", ServiceCalendar.Kind.MEETING, ""),
    ("Church LED Screen Project Discussion", ServiceCalendar.Kind.MEETING, ""),
    ("Artur In-person LED Screen Project", ServiceCalendar.Kind.MEETING, "Artur"),
    ("Vitaly In-person LED Screen Project", ServiceCalendar.Kind.MEETING, "Vitaly"),
    ("Omni LED Interview", ServiceCalendar.Kind.MEETING, "Omni"),
    ("LED Screen Rental", ServiceCalendar.Kind.RENTAL, ""),
)

FUNNELS = (
    (
        "SALES Quote — WP Website",
        "Имя, почта, телефон, город и провинция, срок проекта.\nКнопка Get a Free Quotation.\nСделка New Lead.",
    ),
    (
        "RENTAL Quote — WP Website",
        "Имя, почта, телефон, дата события, локация.\nКнопка Get a Free Quote.\nСделка New Lead, задача аренда.",
    ),
    (
        "SALES Catalog — WP Website Pop Up",
        "Всплывающий каталог продажи.\nОставляет контакт и ставит письмо с каталогом.",
    ),
    (
        "RENTAL Catalog — WP Website Pop Up",
        "Всплывающий каталог аренды.\nОставляет контакт и ставит письмо с каталогом.",
    ),
)

MEETING_STAGES = {
    ServiceCustomer.Stage.NEW_LEAD,
    ServiceCustomer.Stage.CONTACTED,
    ServiceCustomer.Stage.REPLIED,
    ServiceCustomer.Stage.QUALIFIED,
}


def ensure_calendars(subsystem):
    for name, kind, owner in CALENDARS:
        ServiceCalendar.objects.get_or_create(
            subsystem=subsystem,
            name=name,
            defaults={"kind": kind, "owner_name": owner, "minutes": 30, "active": True},
        )
    return ServiceCalendar.objects.filter(subsystem=subsystem)


def ensure_funnels(subsystem):
    for name, steps in FUNNELS:
        ServiceFunnel.objects.get_or_create(
            subsystem=subsystem,
            name=name,
            defaults={"steps": steps, "status": ServiceFunnel.Status.ACTIVE},
        )
    return ServiceFunnel.objects.filter(subsystem=subsystem)


def book_appointment(*, calendar, customer, starts_at, note=""):
    from delayu.models_service import ServiceAppointment

    deal = customer.deals.exclude(status=ServiceDeal.Status.LOST).order_by("-updated_at").first()
    appointment = ServiceAppointment.objects.create(
        subsystem=customer.subsystem,
        calendar=calendar,
        customer=customer,
        deal=deal,
        starts_at=starts_at,
        minutes=calendar.minutes,
        note=note,
    )
    if deal is not None and deal.stage in MEETING_STAGES:
        from delayu.services.service_process import meeting_advances

        if meeting_advances(deal):
            move_deal(deal, ServiceCustomer.Stage.MEETING)
    return appointment


def next_invoice_number(subsystem) -> str:
    seq = 0
    for value in ServiceInvoice.objects.filter(subsystem=subsystem).values_list("number", flat=True):
        tail = str(value).rsplit("-", 1)[-1]
        if tail.isdigit():
            seq = max(seq, int(tail))
    return f"INV-{seq + 1:04d}"


def apply_invoice_state(invoice):
    customer = invoice.customer
    deal = invoice.deal
    if deal is None:
        deal = customer.deals.exclude(status=ServiceDeal.Status.LOST).order_by("-updated_at").first()
        if deal is not None:
            invoice.deal = deal
            invoice.save(update_fields=["deal"])
    if invoice.status == ServiceInvoice.Status.SENT:
        customer.payment_state = ServiceCustomer.PaymentState.INVOICED
        customer.invoice_amount = invoice.amount
        customer.save(update_fields=["payment_state", "invoice_amount", "updated_at"])
        if deal is not None and deal.stage not in {ServiceCustomer.Stage.WON, ServiceCustomer.Stage.INVOICE}:
            move_deal(deal, ServiceCustomer.Stage.INVOICE, actor="счёт")
    elif invoice.status == ServiceInvoice.Status.PAID:
        customer.payment_state = ServiceCustomer.PaymentState.PAID
        customer.invoice_amount = invoice.amount
        customer.save(update_fields=["payment_state", "invoice_amount", "updated_at"])


def issue_invoice(*, customer, title: str, amount, status: str):
    deal = customer.deals.exclude(status=ServiceDeal.Status.LOST).order_by("-updated_at").first()
    invoice = ServiceInvoice.objects.create(
        subsystem=customer.subsystem,
        customer=customer,
        deal=deal,
        number=next_invoice_number(customer.subsystem),
        title=title,
        amount=amount,
        status=status,
        issued_on=timezone.localdate(),
    )
    apply_invoice_state(invoice)
    return invoice


def deliver_mailing(mailing) -> int:
    from delayu.services.service_dialogue import ServiceFlowError, post_message

    customers = ServiceCustomer.objects.filter(subsystem=mailing.subsystem)
    if mailing.audience:
        customers = customers.filter(tags__icontains=mailing.audience)
    sent = 0
    text = f"{mailing.subject}\n{mailing.body}".strip()
    for customer in customers:
        try:
            post_message(
                customer=customer,
                channel="email",
                direction=ServiceMessage.Direction.OUT,
                author_kind=ServiceMessage.AuthorKind.AGENT,
                body=text,
            )
        except ServiceFlowError:
            continue
        sent += 1
    return sent


def send_mailing(*, subsystem, subject: str, body: str, audience: str):
    from delayu.models_service import ServiceMailing

    mailing = ServiceMailing.objects.create(
        subsystem=subsystem, subject=subject, body=body, audience=audience
    )
    mailing.sent_count = deliver_mailing(mailing)
    mailing.save(update_fields=["sent_count"])
    return mailing


def update_mailing(mailing, *, subject: str, body: str, audience: str, resend: bool = False):
    mailing.subject = subject
    mailing.body = body
    mailing.audience = audience
    mailing.save(update_fields=["subject", "body", "audience"])
    if resend:
        mailing.sent_count = mailing.sent_count + deliver_mailing(mailing)
        mailing.save(update_fields=["sent_count"])
    return mailing


def open_ad_lead(*, ad: ServiceAd, display_name: str, phone: str):
    from delayu.services.service_intake import _next_customer_number

    customer = ServiceCustomer.objects.create(
        subsystem=ad.subsystem,
        number=_next_customer_number(ad.subsystem),
        display_name=display_name,
        phone=phone,
        state=ad.province,
        stage=ServiceCustomer.Stage.NEW_LEAD,
        tags=ad.network.lower(),
    )
    source = " ".join(part for part in (ad.network, ad.province, ad.name) if part)
    deal = create_deal(
        customer=customer,
        title=display_name,
        stage=ServiceCustomer.Stage.NEW_LEAD,
        job_type=ad.job_type,
        source=source,
        state=ad.province,
    )
    return customer, deal


def next_custom_code(subsystem) -> str:
    from delayu.models_service import ServiceWorkflow

    seq = ServiceWorkflow.objects.filter(subsystem=subsystem, code__startswith="custom-").count() + 1
    return f"custom-{seq:04d}"
