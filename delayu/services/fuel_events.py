"""Журнал событий контура «Топливный пропуск»."""
from __future__ import annotations

from delayu.models import Subsystem
from delayu.models_fuel import FuelAzsStation, FuelCitizen, FuelEventLog


def log_fuel_event(
    subsystem: Subsystem,
    channel: str,
    action: str,
    summary: str,
    *,
    user=None,
    azs: FuelAzsStation | None = None,
    citizen: FuelCitizen | None = None,
    actor_label: str = "",
    object_type: str = "",
    object_id: str = "",
    payload: dict | None = None,
    request=None,
) -> FuelEventLog:
    if not actor_label:
        if user and getattr(user, "is_authenticated", False):
            actor_label = user.get_full_name() or user.get_username()
        elif azs:
            actor_label = azs.name
        elif citizen:
            actor_label = citizen.full_name or citizen.phone

    entry = FuelEventLog.objects.create(
        subsystem=subsystem,
        channel=channel,
        action=action,
        summary=summary[:512],
        actor_label=actor_label[:255],
        user=user if user and getattr(user, "is_authenticated", False) else None,
        azs=azs,
        citizen=citizen,
        object_type=object_type,
        object_id=str(object_id) if object_id else "",
        payload=payload or {},
    )

    if channel == FuelEventLog.Channel.OPERATOR and user and getattr(user, "is_authenticated", False):
        from delayu.services import audit

        audit.log_action(
            user,
            subsystem,
            f"fuel.{action}",
            object_type,
            object_id,
            payload=payload,
            request=request,
        )
    return entry


def operator_live_payload(subsystem: Subsystem) -> dict:
    """Снимок для онлайн-обновления панели оператора."""
    from django.utils import timezone

    from delayu.models_fuel import FuelApplication, FuelAzsStation, FuelRedeem
    from delayu.services.fuel import operator_dashboard

    stats = operator_dashboard(subsystem)
    pending = (
        FuelApplication.objects.filter(
            subsystem=subsystem, status=FuelApplication.Status.PENDING
        )
        .select_related("citizen", "category")
        .order_by("created_at")[:15]
    )
    redeems = (
        FuelRedeem.objects.filter(subsystem=subsystem)
        .select_related("azs", "permit")
        .order_by("-created_at")[:10]
    )
    stations = (
        subsystem.fuel_azs_stations.filter(is_archived=False)
        .order_by("name")
        .values(
            "id",
            "name",
            "stock_liters",
            "queue_minutes",
            "status",
            "is_accepting_permits",
            "portal_blocked",
        )
    )
    return {
        "ok": True,
        "updated_at": timezone.now().isoformat(),
        "stats": stats,
        "pending_apps": [
            {
                "id": a.pk,
                "number": a.number,
                "plate": a.plate,
                "citizen": a.citizen.full_name or a.citizen.phone,
                "category": a.category.name,
                "created_at": a.created_at.isoformat(),
            }
            for a in pending
        ],
        "recent_redeems": [
            {
                "id": r.pk,
                "plate": r.plate,
                "liters": float(r.liters),
                "azs": r.azs.name,
                "permit": r.permit.number,
                "created_at": r.created_at.isoformat(),
            }
            for r in redeems
        ],
        "stations": list(stations),
    }
