from django.conf import settings
from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestProjectSite, InvestSite

ACTIVE_ROLES = (InvestProjectSite.Role.BOOKED, InvestProjectSite.Role.SELECTED)
DEFAULT_BOOKING_COMPLETENESS_THRESHOLD = 60


class InvestBookingError(Exception):
    pass


def booking_completeness_threshold() -> int:
    return int(
        getattr(
            settings,
            "INVEST_SITE_BOOKING_COMPLETENESS_THRESHOLD",
            DEFAULT_BOOKING_COMPLETENESS_THRESHOLD,
        )
    )


@transaction.atomic
def book_site(*, project, site, user, override_completeness_gate: bool = False) -> InvestProjectSite:
    site = InvestSite.objects.select_for_update().get(pk=site.pk)
    if project.subsystem_id != site.subsystem_id:
        raise InvestBookingError(
            "Проект и площадка принадлежат разным подсистемам"
        )
    threshold = booking_completeness_threshold()
    if site.completeness_pct < threshold and not override_completeness_gate:
        raise InvestBookingError(
            f"Бронирование недоступно: полнота карточки площадки {site.completeness_pct}% ниже порога {threshold}%"
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
    from delayu.services.invest_extracts import ensure_extract_for_site
    from delayu.services.invest_fgistp import ensure_fgistp_for_site

    ensure_extract_for_site(site, reason="booking", user=user, project=project)
    ensure_fgistp_for_site(site, reason="booking", user=user, project=project)
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
