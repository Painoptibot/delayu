"""Прогноз очереди и ёмкости АЗС."""
from __future__ import annotations

from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_fuel import FuelApplication, FuelAzsStation, FuelPermit, FuelPortalSettings


def get_portal_settings(subsystem: Subsystem) -> FuelPortalSettings:
    obj, _ = FuelPortalSettings.objects.get_or_create(subsystem=subsystem)
    return obj


def azs_directed_permits_count(azs: FuelAzsStation) -> int:
    now = timezone.now()
    return FuelPermit.objects.filter(
        assigned_azs=azs,
        status=FuelPermit.Status.ACTIVE,
        valid_until__gte=now,
        remaining_liters__gt=0,
    ).count()


def azs_pending_apps_count(azs: FuelAzsStation) -> int:
    return FuelApplication.objects.filter(
        assigned_azs=azs,
        status=FuelApplication.Status.PENDING,
    ).count()


def azs_apps_submitted_count(azs: FuelAzsStation) -> int:
    return azs_pending_apps_count(azs) + azs_directed_permits_count(azs)


def azs_redeemed_today_count(azs: FuelAzsStation) -> int:
    from delayu.models_fuel import FuelRedeem

    today = timezone.localdate()
    return FuelRedeem.objects.filter(azs=azs, created_at__date=today).count()


def compute_max_applications(azs: FuelAzsStation, settings: FuelPortalSettings) -> int:
    if azs.max_apps_override is not None:
        return int(azs.max_apps_override)
    quota = max(1, int(settings.permit_quota_liters))
    return max(0, int(azs.stock_liters) // quota)


def compute_queue_minutes(azs: FuelAzsStation, settings: FuelPortalSettings) -> int:
    if azs.use_manual_queue:
        return int(azs.queue_minutes)
    if not settings.auto_queue_enabled:
        return int(azs.queue_minutes)
    pumps = max(1, int(azs.pump_count))
    avg_min = max(1, int(azs.avg_refuel_minutes))
    waiting = azs_apps_submitted_count(azs)
    if waiting <= 0:
        return 0
    throughput_per_hour = pumps * (60 / avg_min)
    if throughput_per_hour <= 0:
        return int(azs.queue_minutes)
    hours_wait = waiting / throughput_per_hour
    return max(0, min(999, int(hours_wait * 60)))


def azs_capacity_snapshot(azs: FuelAzsStation, settings: FuelPortalSettings | None = None) -> dict:
    settings = settings or get_portal_settings(azs.subsystem)
    submitted = azs_apps_submitted_count(azs)
    redeemed = azs_redeemed_today_count(azs)
    max_apps = compute_max_applications(azs, settings)
    remaining = max(0, max_apps - submitted)
    queue = compute_queue_minutes(azs, settings)
    return {
        "apps_submitted": submitted,
        "apps_redeemed_today": redeemed,
        "apps_remaining": remaining,
        "max_applications": max_apps,
        "queue_minutes_computed": queue,
        "pump_count": azs.pump_count,
        "avg_refuel_minutes": azs.avg_refuel_minutes,
        "permit_quota_liters": settings.permit_quota_liters,
    }


def refresh_azs_queue(azs: FuelAzsStation, *, save: bool = True) -> FuelAzsStation:
    settings = get_portal_settings(azs.subsystem)
    if azs.use_manual_queue:
        return azs
    azs.queue_minutes = compute_queue_minutes(azs, settings)
    if save:
        azs.save(update_fields=["queue_minutes", "updated_at"])
    return azs
