"""Срок первого ответа, сообщение о стадии, квалификация и дожим."""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from delayu.models_service import ServiceCustomer, ServiceDeal, ServiceMessage

SALE_PROVINCES = {"AB", "ON", "QC"}
RENTAL_PROVINCES = {"AB", "QC"}
EARLY_STAGES = {
    ServiceCustomer.Stage.NEW_LEAD,
    ServiceCustomer.Stage.CONTACTED,
    ServiceCustomer.Stage.REPLIED,
}
FIRST_RESPONSE_AFTER = timedelta(hours=1)
PROVINCE_NAMES = {
    "AB": "AB",
    "ALBERTA": "AB",
    "ON": "ON",
    "ONTARIO": "ON",
    "QC": "QC",
    "QUEBEC": "QC",
    "QB": "QC",
    "BC": "BC",
    "BRITISH COLUMBIA": "BC",
    "MB": "MB",
    "MANITOBA": "MB",
    "SK": "SK",
    "SASKATCHEWAN": "SK",
}


def province_code(value: str) -> str:
    text = (value or "").strip().upper()
    return PROVINCE_NAMES.get(text, text[:2] if len(text) >= 2 else text)


def schedule_first_response(deal: ServiceDeal) -> bool:
    """Через час в карточку попадает актуальное сообщение о стадии, если ответа ещё не было."""
    from delayu.services.service_agent import queue_notice
    from delayu.services.service_dialogue import ServiceFlowError

    if deal.customer.messages.filter(kind=ServiceMessage.Kind.STAGE).exists():
        return False
    try:
        queue_notice(
            customer=deal.customer,
            channel="sms",
            kind=ServiceMessage.Kind.STAGE,
            scheduled_for=timezone.now() + FIRST_RESPONSE_AFTER,
        )
    except ServiceFlowError:
        return False
    return True


def announce_stage(deal: ServiceDeal) -> None:
    from delayu.services.service_agent import compose_stage
    from delayu.services.service_dialogue import ServiceFlowError, post_message

    try:
        post_message(
            customer=deal.customer,
            channel="sms",
            direction=ServiceMessage.Direction.OUT,
            author_kind=ServiceMessage.AuthorKind.AGENT,
            kind=ServiceMessage.Kind.STAGE,
            body=compose_stage(deal.customer),
        )
    except ServiceFlowError:
        return


def _missing(deal: ServiceDeal) -> list[str]:
    code = province_code(deal.state)
    if deal.job_type == ServiceCustomer.JobType.RENTAL:
        gaps = []
        if deal.guests_over_200 != ServiceDeal.Answer.YES:
            gaps.append("гости не больше 200")
        if code not in RENTAL_PROVINCES:
            gaps.append("провинция аренды не AB и не QC")
        return gaps
    gaps = []
    if deal.decision_maker != ServiceDeal.Answer.YES:
        gaps.append("не подтверждено, что это лицо принимает решение")
    if deal.screen_over_30 != ServiceDeal.Answer.YES:
        gaps.append("экран не больше 30 кв. футов")
    if code not in SALE_PROVINCES:
        gaps.append("провинция продажи не AB, ON или QC")
    return gaps


def _mark_church(deal: ServiceDeal) -> None:
    if deal.church_project != ServiceDeal.Answer.YES:
        return
    customer = deal.customer
    tags = [part.strip() for part in (customer.tags or "").split(",") if part.strip()]
    if "church" in tags:
        return
    tags.append("church")
    customer.tags = ", ".join(tags)
    customer.save(update_fields=["tags", "updated_at"])


def qualify_deal(deal: ServiceDeal) -> str:
    """Переносит раннюю сделку в Qualified, когда правила покупки или аренды выполнены."""
    _mark_church(deal)
    gaps = _missing(deal)
    if gaps:
        deal.qualification = "Не квалифицирована: " + "; ".join(gaps)
        deal.save(update_fields=["qualification", "updated_at"])
        return deal.qualification
    deal.qualification = "Квалифицирована"
    deal.save(update_fields=["qualification", "updated_at"])
    if deal.status != ServiceDeal.Status.LOST and deal.stage in EARLY_STAGES:
        from delayu.services.service_deals import move_deal

        move_deal(deal, ServiceCustomer.Stage.QUALIFIED)
    return deal.qualification


def _queue_followup(deal: ServiceDeal, *, channel: str, body: str, after: timedelta) -> None:
    from delayu.services.service_dialogue import ServiceFlowError, post_message

    if deal.customer.messages.filter(body__startswith=body.split(":", 1)[0] + ":").exists():
        return
    try:
        post_message(
            customer=deal.customer,
            channel=channel,
            direction=ServiceMessage.Direction.OUT,
            author_kind=ServiceMessage.AuthorKind.AGENT,
            kind=ServiceMessage.Kind.DIALOGUE,
            body=body,
            scheduled_for=timezone.now() + after,
        )
    except ServiceFlowError:
        return


def send_catalog(deal: ServiceDeal) -> None:
    _queue_followup(
        deal,
        channel="email",
        body=(
            "Catalog: the Canadian LED screen catalog is ready. "
            "Reply and we will size the wall with you."
        ),
        after=timedelta(days=1),
    )


def send_church(deal: ServiceDeal) -> None:
    _queue_followup(
        deal,
        channel="email",
        body=(
            "Church LED: how to choose a church LED screen. "
            "We can walk through size, brightness and installation."
        ),
        after=timedelta(days=2),
    )


def send_province(deal: ServiceDeal) -> None:
    code = province_code(deal.state)
    if not code:
        return
    _queue_followup(
        deal,
        channel="sms",
        body=(
            f"Province follow-up: a specialist for {code} will contact you "
            "about your LED screen project."
        ),
        after=timedelta(days=1),
    )


def plan_followups(deal: ServiceDeal, *, catalog: bool = False) -> None:
    """Каталог, церковное письмо и дожим по провинции. Повторно те же письма не ставит."""
    if catalog or "catalog" in (deal.source or "").lower():
        send_catalog(deal)
    if deal.church_project == ServiceDeal.Answer.YES:
        send_church(deal)
    send_province(deal)


WORKFLOW_SEEDS = (
    ("first-response", "General Automations", "Lead Created — Timestamp & SLA Timer", "deal_created", "first_response"),
    ("announce-stage", "General Automations", "Stage change — customer SMS", "stage_changed", "announce_stage"),
    ("qualify", "Sales Automations", "Qualify LED lead", "deal_ready", "qualify"),
    ("catalog", "WEBSITE Forms", "Website Form — Send a SALES CATALOG", "deal_ready", "catalog"),
    ("church", "NURTURE - SALES", "Church — Nurture Email #1", "deal_ready", "church"),
    ("province", "Sales Automations", "Province follow-up", "deal_ready", "province"),
)


def ensure_workflows(subsystem):
    from delayu.models_service import ServiceWorkflow

    for code, folder, name, trigger, action in WORKFLOW_SEEDS:
        ServiceWorkflow.objects.get_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "folder": folder,
                "name": name,
                "trigger": trigger,
                "action": action,
                "status": ServiceWorkflow.Status.PUBLISHED,
            },
        )
    from delayu.services.service_snapshot import load_workflows

    load_workflows(subsystem)
    return ServiceWorkflow.objects.filter(subsystem=subsystem)


def run_workflows(deal: ServiceDeal, trigger: str, *, catalog: bool = False) -> int:
    """Запускает опубликованные сценарии события. Черновик не срабатывает."""
    from delayu.models_service import ServiceWorkflow

    ensure_workflows(deal.subsystem)
    ran = 0
    workflows = ServiceWorkflow.objects.filter(
        subsystem=deal.subsystem,
        status=ServiceWorkflow.Status.PUBLISHED,
        trigger=trigger,
    )
    for workflow in workflows:
        acted = _run_action(workflow.action, deal, catalog=catalog)
        if not acted:
            continue
        workflow.enrolled += 1
        workflow.save(update_fields=["enrolled"])
        ran += 1
    return ran


def _run_action(action: str, deal: ServiceDeal, *, catalog: bool) -> bool:
    if action == "first_response":
        return schedule_first_response(deal)
    if action == "announce_stage":
        announce_stage(deal)
        return True
    if action == "qualify":
        qualify_deal(deal)
        return True
    if action == "catalog":
        if not (catalog or "catalog" in (deal.source or "").lower()):
            return False
        send_catalog(deal)
        return True
    if action == "church":
        if deal.church_project != ServiceDeal.Answer.YES:
            return False
        send_church(deal)
        return True
    if action == "province":
        if not province_code(deal.state):
            return False
        send_province(deal)
        return True
    return False
