"""Издержки выезда и силы, затраченные на объект."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from delayu.models_service import money


def apply_visit_costs(visit) -> None:
    distance = Decimal(visit.distance_mi or 0)
    rate = Decimal(visit.rate_per_mile or 0)
    hours = Decimal(visit.hours or 0)
    hour_rate = Decimal(visit.hour_rate or 0)
    other = Decimal(visit.other_cost or 0)
    visit.travel_cost = money(distance * rate)
    visit.labor_cost = money(hours * hour_rate)
    visit.other_cost = money(other)
    visit.total_cost = money(visit.travel_cost + visit.labor_cost + visit.other_cost)


def apply_deployment_costs(row) -> None:
    quantity = Decimal(row.quantity or 0)
    unit_cost = Decimal(row.unit_cost or 0)
    row.unit_cost = money(unit_cost)
    row.total_cost = money(quantity * unit_cost)


def _sum(qs, field: str):
    return money(qs.aggregate(total=Sum(field))["total"])


def object_totals(site) -> dict:
    visits = site.visits.all()
    forces = site.deployments.all()
    travel = _sum(visits, "travel_cost")
    labor = _sum(visits, "labor_cost")
    other = _sum(visits, "other_cost")
    resources = _sum(forces, "total_cost")
    return {
        "travel": travel,
        "labor": labor,
        "other": other,
        "visits": money(travel + labor + other),
        "resources": resources,
        "total": money(travel + labor + other + resources),
        "people": forces.filter(kind="people").count(),
        "visit_count": visits.count(),
    }


def customer_totals(customer) -> dict:
    from delayu.models_service import ServiceDeployment, ServiceVisit

    visits = ServiceVisit.objects.filter(site__customer=customer)
    forces = ServiceDeployment.objects.filter(site__customer=customer)
    travel = _sum(visits, "travel_cost")
    labor = _sum(visits, "labor_cost")
    other = _sum(visits, "other_cost")
    resources = _sum(forces, "total_cost")
    return {
        "travel": travel,
        "labor": labor,
        "other": other,
        "resources": resources,
        "total": money(travel + labor + other + resources),
    }
