from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestProjectSite, InvestSite

ACTIVE_ROLES = (InvestProjectSite.Role.BOOKED, InvestProjectSite.Role.SELECTED)


class InvestBookingError(Exception):
    pass


@transaction.atomic
def book_site(*, project, site, user) -> InvestProjectSite:
    site = InvestSite.objects.select_for_update().get(pk=site.pk)
    if project.subsystem_id != site.subsystem_id:
        raise InvestBookingError(
            "Проект и площадка принадлежат разным подсистемам"
        )
    conflict = (
        InvestProjectSite.objects.select_for_update()
        .filter(site=site, role__in=ACTIVE_ROLES)
        .exclude(project=project)
        .select_related("project")
        .first()
    )
    if conflict:
        raise InvestBookingError(
            f"Площадка занята проектом {conflict.project.code} ({conflict.get_role_display()})"
        )
    link, _ = InvestProjectSite.objects.update_or_create(
        project=project, site=site, defaults={"role": InvestProjectSite.Role.BOOKED}
    )
    return link


@transaction.atomic
def select_site(*, project, site, user) -> InvestProjectSite:
    book_site(project=project, site=site, user=user)
    link = InvestProjectSite.objects.get(project=project, site=site)
    # снять selected с других площадок этого проекта
    InvestProjectSite.objects.filter(project=project, role=InvestProjectSite.Role.SELECTED).exclude(
        pk=link.pk
    ).update(role=InvestProjectSite.Role.PROPOSED)
    link.role = InvestProjectSite.Role.SELECTED
    link.save(update_fields=["role", "updated_at"])
    return link


@transaction.atomic
def expire_overdue_bookings(*, subsystem=None, now=None) -> int:
    now = now or timezone.now()
    qs = InvestProjectSite.objects.select_for_update().filter(
        role=InvestProjectSite.Role.BOOKED,
        booked_until__isnull=False,
        booked_until__lte=now,
    )
    if subsystem is not None:
        qs = qs.filter(project__subsystem=subsystem)
    count = qs.count()
    qs.update(role=InvestProjectSite.Role.CANDIDATE, booked_until=None, updated_at=now)
    return count
