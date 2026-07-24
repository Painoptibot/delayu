"""Handoff service; funnel edits stay service-only until Task 8 forms."""

from django.db import transaction
from django.utils import timezone

from delayu.menu import get_active_membership
from delayu.models_invest import InvestHandoff, InvestProject
from delayu.services.invest_package import package_is_ready
from delayu.services.invest_roadmap import seed_support_roadmap


class InvestHandoffError(Exception):
    pass


def _require_handoff_role(*, user, project, allowed_roles, message):
    membership = get_active_membership(user, project.subsystem_id)
    if not membership or membership.role.code not in allowed_roles:
        raise InvestHandoffError(message)
    return membership


@transaction.atomic
def request_handoff(*, project, user, comment=""):
    _require_handoff_role(
        user=user,
        project=project,
        allowed_roles={"invest_agency", "invest_admin"},
        message="Передачу может запросить только агентство",
    )
    if project.funnel != InvestProject.Funnel.ATTRACTION:
        raise InvestHandoffError("Передача только из воронки привлечения")
    return InvestHandoff.objects.create(
        project=project,
        requested_by=user,
        comment=comment,
        status=InvestHandoff.Status.REQUESTED,
    )


@transaction.atomic
def accept_handoff(*, handoff, user):
    _require_handoff_role(
        user=user,
        project=handoff.project,
        allowed_roles={"invest_dept", "invest_admin"},
        message="Решение по передаче доступно только департаменту",
    )
    if handoff.status != InvestHandoff.Status.REQUESTED:
        raise InvestHandoffError("Решение уже принято")
    if not package_is_ready(handoff.project):
        raise InvestHandoffError("Пакет не готов: есть обязательные пункты missing")
    handoff.status = InvestHandoff.Status.ACCEPTED
    handoff.decided_by = user
    handoff.decided_at = timezone.now()
    handoff.save()
    p = handoff.project
    p.funnel = InvestProject.Funnel.SUPPORT
    p.stage = "accepted"
    p.save(update_fields=["funnel", "stage", "updated_at"])
    seed_support_roadmap(p)
    return p


@transaction.atomic
def return_handoff(*, handoff, user, comment):
    _require_handoff_role(
        user=user,
        project=handoff.project,
        allowed_roles={"invest_dept", "invest_admin"},
        message="Решение по передаче доступно только департаменту",
    )
    if handoff.status != InvestHandoff.Status.REQUESTED:
        raise InvestHandoffError("Решение уже принято")
    handoff.status = InvestHandoff.Status.RETURNED
    handoff.decided_by = user
    handoff.decided_at = timezone.now()
    handoff.comment = comment
    handoff.save()
    return handoff
