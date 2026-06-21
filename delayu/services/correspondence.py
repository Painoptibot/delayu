"""M24–M32 — корреспонденция, журнал, маршрутизация, печать, ЭП."""
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from delayu.models import (
    Correspondence,
    CorrespondenceEvent,
    CorrespondenceRoute,
    PrintTemplate,
    RegistrationJournalEntry,
)
from delayu.services.domain import atomic_service
from delayu.services.numbering import next_reg_number as _next_reg_number


def next_reg_number(subsystem, direction: str) -> str:
    return _next_reg_number(subsystem, direction)


def filter_correspondence(subsystem, *, direction=None, params=None):
    params = params or {}
    qs = Correspondence.objects.filter(subsystem=subsystem).select_related(
        "assignee", "case", "linked_incoming", "created_by"
    )
    if direction:
        qs = qs.filter(direction=direction)
    q = (params.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(reg_number__icontains=q)
            | Q(subject__icontains=q)
            | Q(counterparty__icontains=q)
        )
    status = params.get("status", "").strip()
    if status:
        qs = qs.filter(status=status)
    if params.get("year"):
        qs = qs.filter(reg_date__year=int(params["year"]))
    return qs.order_by("-reg_date", "-reg_number")


def log_event(correspondence, event_type, description, *, actor=None, document=None):
    return CorrespondenceEvent.objects.create(
        correspondence=correspondence,
        document=document,
        event_type=event_type,
        description=description[:500],
        actor=actor,
    )


@atomic_service
def register_correspondence(
    *,
    subsystem,
    user,
    direction,
    subject,
    counterparty="",
    assignee=None,
    case=None,
    status=None,
    linked_incoming=None,
    reg_number=None,
    reg_date=None,
):
    corr = Correspondence.objects.create(
        subsystem=subsystem,
        direction=direction,
        reg_number=reg_number or next_reg_number(subsystem, direction),
        reg_date=reg_date or timezone.now().date(),
        subject=subject,
        counterparty=counterparty,
        assignee=assignee,
        case=case,
        status=status
        or (
            Correspondence.Status.REGISTERED
            if direction == Correspondence.Direction.IN
            else Correspondence.Status.REGISTERED
        ),
        created_by=user,
        linked_incoming=linked_incoming,
    )
    RegistrationJournalEntry.objects.get_or_create(
        correspondence=corr, defaults={"operator": user}
    )
    log_event(
        corr,
        CorrespondenceEvent.EventType.REGISTERED,
        f"Зарегистрировано {corr.get_direction_display()} {corr.reg_number}",
        actor=user,
    )
    if case:
        log_event(
            corr,
            CorrespondenceEvent.EventType.LINKED,
            f"Привязано к делу {case.number}",
            actor=user,
        )
    return corr


@atomic_service
def register_inbound_enhanced(
    *,
    subsystem,
    organization,
    user,
    subject,
    counterparty="",
    assignee=None,
    case=None,
    status=None,
    reg_date=None,
    create_case=False,
    new_case_title="",
):
    """#35 — регистрация входящего с опциональным созданием дела и подсказкой ИИ."""
    from delayu.models import CaseFile
    from delayu.services.ai import classify_correspondence
    from delayu.services.cases import next_case_number

    ai_hint = classify_correspondence(subject)
    linked_case = case
    if create_case and not linked_case:
        title = (new_case_title or subject).strip()
        if title:
            linked_case = CaseFile.objects.create(
                subsystem=subsystem,
                organization=organization,
                number=next_case_number(subsystem),
                created_by=user,
                title=title,
                assignee=assignee,
                priority=ai_hint.get("priority", 3),
                status=CaseFile.Status.NEW,
            )
    corr = register_correspondence(
        subsystem=subsystem,
        user=user,
        direction=Correspondence.Direction.IN,
        subject=subject,
        counterparty=counterparty,
        assignee=assignee,
        case=linked_case,
        status=status,
        reg_date=reg_date,
    )
    return corr, linked_case, ai_hint


@atomic_service
def route_correspondence(correspondence, from_user, to_user, comment=""):
    CorrespondenceRoute.objects.create(
        correspondence=correspondence,
        from_user=from_user,
        to_user=to_user,
        comment=comment,
    )
    correspondence.assignee = to_user
    correspondence.status = Correspondence.Status.IN_WORK
    correspondence.save(update_fields=["assignee", "status"])
    log_event(
        correspondence,
        CorrespondenceEvent.EventType.ROUTED,
        f"Передано {to_user}: {comment[:200] if comment else 'без комментария'}",
        actor=from_user,
    )
    from delayu.services.notify_dispatch import notify_correspondence_routed

    notify_correspondence_routed(correspondence, from_user, to_user, comment)


def render_print_template(template: PrintTemplate, correspondence: Correspondence) -> str:
    body = template.body
    replacements = {
        "{{reg_number}}": correspondence.reg_number,
        "{{subject}}": correspondence.subject,
        "{{counterparty}}": correspondence.counterparty,
        "{{reg_date}}": correspondence.reg_date.isoformat(),
        "{{direction}}": correspondence.get_direction_display(),
        "{{status}}": correspondence.get_status_display(),
    }
    for key, val in replacements.items():
        body = body.replace(key, val)
    return body
