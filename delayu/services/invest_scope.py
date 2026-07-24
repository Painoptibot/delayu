"""Queryset scope for invest roles (org filter for MO)."""
from __future__ import annotations

from django.db.models import QuerySet

from delayu.models_invest import InvestProject, InvestSite
from delayu.services.invest_roles import ROLE_SPECS

INVEST_ROLE_CODES = frozenset(ROLE_SPECS)


def projects_for_membership(membership) -> QuerySet[InvestProject]:
    role_code = membership.role.code
    if role_code not in INVEST_ROLE_CODES:
        return InvestProject.objects.none()

    qs = InvestProject.objects.filter(subsystem=membership.subsystem)
    if role_code == "invest_mo":
        return qs.filter(organization=membership.organization)
    return qs


def sites_for_membership(membership) -> QuerySet[InvestSite]:
    role_code = membership.role.code
    if role_code not in INVEST_ROLE_CODES:
        return InvestSite.objects.none()

    qs = InvestSite.objects.filter(subsystem=membership.subsystem)
    if role_code == "invest_mo":
        return qs.filter(organization=membership.organization)
    return qs
