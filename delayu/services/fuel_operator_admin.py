"""Администрирование АЗС и чёрного списка — оператор штаба."""
from __future__ import annotations

import re
import secrets
import string

from django.utils import timezone
from django.utils.text import slugify

from delayu.models import Subsystem
from delayu.models_fuel import FuelAzsStation, FuelBlacklistEntry
from delayu.services.fuel import normalize_inn, normalize_plate
from delayu.services.fuel_events import log_fuel_event


def _unique_azs_code(subsystem: Subsystem, base: str) -> str:
    code = base[:32] or "azs"
    if not FuelAzsStation.objects.filter(subsystem=subsystem, code=code).exists():
        return code
    for i in range(2, 1000):
        candidate = f"{code[:28]}-{i}"
        if not FuelAzsStation.objects.filter(subsystem=subsystem, code=candidate).exists():
            return candidate
    return f"{code[:24]}-{secrets.token_hex(3)}"


def _slug_code(name: str) -> str:
    raw = slugify(name, allow_unicode=False) or "azs"
    return re.sub(r"[^a-z0-9-]", "", raw.lower())[:32]


def _gen_portal_login(subsystem: Subsystem, name: str) -> str:
    base = _slug_code(name).replace("-", "")[:20] or "azs"
    login = base
    n = 1
    while FuelAzsStation.objects.filter(subsystem=subsystem, portal_login=login).exists():
        n += 1
        login = f"{base}{n}"[:64]
    return login


def _gen_portal_pin(length: int = 4) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def create_azs_station(subsystem: Subsystem, data: dict, *, user=None, request=None) -> FuelAzsStation:
    name = data["name"].strip()
    code = (data.get("code") or "").strip() or _unique_azs_code(subsystem, _slug_code(name))
    portal_login = (data.get("portal_login") or "").strip() or _gen_portal_login(subsystem, name)
    portal_pin = (data.get("portal_pin") or "").strip() or _gen_portal_pin()
    station = FuelAzsStation.objects.create(
        subsystem=subsystem,
        code=_unique_azs_code(subsystem, code),
        name=name,
        network=data.get("network", "").strip(),
        address=data["address"].strip(),
        district=data.get("district", "").strip(),
        latitude=data.get("latitude"),
        longitude=data.get("longitude"),
        status=data.get("status") or FuelAzsStation.Status.OK,
        stock_liters=max(0, int(data.get("stock_liters") or 0)),
        queue_minutes=max(0, min(int(data.get("queue_minutes") or 0), 999)),
        fuel_grade=data.get("fuel_grade", "АИ-95").strip() or "АИ-95",
        is_accepting_permits=bool(data.get("is_accepting_permits", True)),
        portal_login=portal_login,
        portal_pin=portal_pin,
    )
    log_fuel_event(
        subsystem,
        "operator",
        "azs.create",
        f"Добавлена АЗС «{station.name}»",
        user=user,
        object_type="FuelAzsStation",
        object_id=station.pk,
        payload={"code": station.code, "portal_login": station.portal_login},
        request=request,
    )
    return station


def update_azs_station(
    station: FuelAzsStation, data: dict, *, user=None, request=None
) -> FuelAzsStation:
    fields = [
        "name",
        "network",
        "address",
        "district",
        "latitude",
        "longitude",
        "status",
        "stock_liters",
        "queue_minutes",
        "pump_count",
        "avg_refuel_minutes",
        "use_manual_queue",
        "max_apps_override",
        "fuel_grade",
        "is_accepting_permits",
        "portal_login",
        "portal_pin",
        "portal_blocked",
    ]
    for key in fields:
        if key not in data:
            continue
        val = data[key]
        if key in ("stock_liters", "queue_minutes", "pump_count", "avg_refuel_minutes", "max_apps_override"):
            if val in (None, "") and key == "max_apps_override":
                val = None
            else:
                val = max(0, int(val or 0))
                if key == "queue_minutes":
                    val = min(val, 999)
                elif key == "pump_count":
                    val = max(1, val)
                elif key == "avg_refuel_minutes":
                    val = max(1, val)
        elif key in ("use_manual_queue", "portal_blocked", "is_accepting_permits"):
            val = bool(val)
        elif key in ("portal_login", "portal_pin", "name", "network", "address", "district", "fuel_grade"):
            val = str(val or "").strip()
        setattr(station, key, val)
    station.save()
    from delayu.services.fuel_capacity import refresh_azs_queue

    refresh_azs_queue(station)
    log_fuel_event(
        station.subsystem,
        "operator",
        "azs.update",
        f"Изменена АЗС «{station.name}»",
        user=user,
        azs=station,
        object_type="FuelAzsStation",
        object_id=station.pk,
        payload={"name": station.name},
        request=request,
    )
    return station


def archive_azs_station(station: FuelAzsStation, *, user=None, request=None) -> FuelAzsStation:
    station.is_archived = True
    station.archived_at = timezone.now()
    station.is_accepting_permits = False
    station.portal_blocked = True
    station.save(
        update_fields=[
            "is_archived",
            "archived_at",
            "is_accepting_permits",
            "portal_blocked",
            "updated_at",
        ]
    )
    log_fuel_event(
        station.subsystem,
        "operator",
        "azs.archive",
        f"АЗС «{station.name}» перенесена в архив",
        user=user,
        azs=station,
        object_type="FuelAzsStation",
        object_id=station.pk,
        request=request,
    )
    return station


def restore_azs_station(station: FuelAzsStation, *, user=None, request=None) -> FuelAzsStation:
    station.is_archived = False
    station.archived_at = None
    station.save(update_fields=["is_archived", "archived_at", "updated_at"])
    log_fuel_event(
        station.subsystem,
        "operator",
        "azs.restore",
        f"АЗС «{station.name}» восстановлена из архива",
        user=user,
        azs=station,
        object_type="FuelAzsStation",
        object_id=station.pk,
        request=request,
    )
    return station


def toggle_azs_portal_block(
    station: FuelAzsStation, *, user=None, request=None
) -> FuelAzsStation:
    station.portal_blocked = not station.portal_blocked
    station.save(update_fields=["portal_blocked", "updated_at"])
    action = "azs.portal_block" if station.portal_blocked else "azs.portal_unblock"
    summary = (
        f"Доступ к порталу АЗС «{station.name}» заблокирован"
        if station.portal_blocked
        else f"Доступ к порталу АЗС «{station.name}» разблокирован"
    )
    log_fuel_event(
        station.subsystem,
        "operator",
        action,
        summary,
        user=user,
        azs=station,
        object_type="FuelAzsStation",
        object_id=station.pk,
        request=request,
    )
    return station


def deactivate_blacklist_entry(
    entry: FuelBlacklistEntry, *, user=None, request=None
) -> FuelBlacklistEntry:
    if not entry.is_active:
        return entry
    entry.is_active = False
    entry.deactivated_at = timezone.now()
    entry.save(update_fields=["is_active", "deactivated_at"])
    label = entry.plate or entry.inn
    log_fuel_event(
        entry.subsystem,
        "operator",
        "blacklist.deactivate",
        f"Снято ограничение для {label}",
        user=user,
        object_type="FuelBlacklistEntry",
        object_id=entry.pk,
        payload={"plate": entry.plate, "inn": entry.inn, "reason": entry.reason},
        request=request,
    )
    return entry


def reactivate_blacklist_entry(
    entry: FuelBlacklistEntry, *, user=None, request=None
) -> FuelBlacklistEntry:
    if entry.is_active:
        return entry
    entry.is_active = True
    entry.deactivated_at = None
    entry.save(update_fields=["is_active", "deactivated_at"])
    label = entry.plate or entry.inn
    log_fuel_event(
        entry.subsystem,
        "operator",
        "blacklist.reactivate",
        f"Восстановлено ограничение для {label}",
        user=user,
        object_type="FuelBlacklistEntry",
        object_id=entry.pk,
        request=request,
    )
    return entry
