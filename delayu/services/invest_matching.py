"""Автоподбор площадок-кандидатов (п.10–11) и коллизии брони."""
from __future__ import annotations

from decimal import Decimal

from delayu.models_invest import InvestProject, InvestProjectSite, InvestSite
from delayu.services.invest_booking import InvestBookingError


def site_has_active_booking(site: InvestSite) -> bool:
    return InvestProjectSite.objects.filter(
        site=site,
        role__in=(InvestProjectSite.Role.BOOKED, InvestProjectSite.Role.SELECTED),
    ).exists()


def suggest_sites_for_project(project: InvestProject, *, limit: int = 5) -> list[dict]:
    qs = InvestSite.objects.filter(
        subsystem=project.subsystem,
        organization=project.organization,
        status__in=(InvestSite.Status.ACTUAL, InvestSite.Status.IN_REVIEW),
    ).order_by("-completeness_pct", "cadastral_number")
    suggestions = []
    for site in qs[:50]:
        if site_has_active_booking(site):
            continue
        suggestions.append(
            {
                "site_id": site.pk,
                "cadastral_number": site.cadastral_number,
                "name": site.name,
                "area_ha": str(site.area_ha) if site.area_ha is not None else None,
                "vri": site.vri,
                "completeness_pct": site.completeness_pct,
                "score": site.completeness_pct,
            }
        )
        if len(suggestions) >= limit:
            break
    return suggestions


def link_candidate(project: InvestProject, site: InvestSite) -> InvestProjectSite:
    if site.subsystem_id != project.subsystem_id:
        raise InvestBookingError("Площадка из другого контура")
    link, _ = InvestProjectSite.objects.get_or_create(
        project=project,
        site=site,
        defaults={"role": InvestProjectSite.Role.CANDIDATE},
    )
    return link


def auto_attach_candidates(project: InvestProject, *, limit: int = 3) -> list[int]:
    ids = []
    for item in suggest_sites_for_project(project, limit=limit):
        site = InvestSite.objects.get(pk=item["site_id"])
        link = link_candidate(project, site)
        ids.append(link.pk)
    return ids


def filter_by_requirements(
    project: InvestProject,
    *,
    min_area_ha: Decimal | None = None,
    vri_contains: str = "",
) -> list[InvestSite]:
    qs = InvestSite.objects.filter(subsystem=project.subsystem, organization=project.organization)
    if min_area_ha is not None:
        qs = qs.filter(area_ha__gte=min_area_ha)
    if vri_contains:
        qs = qs.filter(vri__icontains=vri_contains)
    return [
        site
        for site in qs.order_by("-completeness_pct")[:20]
        if not site_has_active_booking(site)
    ]
