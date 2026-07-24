"""Handoff service; funnel edits stay service-only until Task 8 forms."""

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestHandoff, InvestProject
from delayu.services.invest_package import package_is_ready
from delayu.services.invest_roadmap import seed_support_roadmap


class InvestHandoffError(Exception):
    pass


@transaction.atomic
def request_handoff(*, project, user, comment=""):
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
    if handoff.status != InvestHandoff.Status.REQUESTED:
        raise InvestHandoffError("Решение уже принято")
    handoff.status = InvestHandoff.Status.RETURNED
    handoff.decided_by = user
    handoff.decided_at = timezone.now()
    handoff.comment = comment
    handoff.save()
    return handoff
