"""Точки МКД и геообъектов подсистемы УЖВ для карты (Яндекс.Карты / M67)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings

from delayu.models_uzhv import MunicipalBuilding
from delayu.services.infra import demo_geocode, geo_objects_for_map


# Центр по умолчанию — Краснодар (демо-данные seed_uzhv)
DEFAULT_CENTER = (45.035, 38.975)
DEFAULT_ZOOM = 12


def _building_color(building: MunicipalBuilding) -> str:
    if building.condition == MunicipalBuilding.Condition.EMERGENCY:
        return "#ff4c51"
    if building.in_resettlement_program or building.condition == MunicipalBuilding.Condition.RENOVATION:
        return "#ff9f43"
    return "#7367f0"


def building_map_point(building: MunicipalBuilding) -> dict | None:
    if not building.has_coordinates:
        return None
    return {
        "id": building.pk,
        "kind": "building",
        "title": building.address[:120],
        "address": building.address,
        "lat": float(building.latitude),
        "lng": float(building.longitude),
        "color": _building_color(building),
        "modal_url": f"/uzhv/fund/{building.pk}/modal/",
        "detail_url": f"/uzhv/fund/{building.pk}/",
        "badge": building.get_condition_display(),
    }


def buildings_for_map(subsystem, *, limit: int = 500) -> list[dict]:
    qs = (
        MunicipalBuilding.objects.filter(subsystem=subsystem)
        .exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .order_by("address")[:limit]
    )
    points = []
    for b in qs:
        pt = building_map_point(b)
        if pt:
            points.append(pt)
    return points


def map_points_for_uzhv(subsystem, *, include_geo_objects: bool = True) -> list[dict]:
    """МКД УЖВ + при наличии — объекты геопортала (M67) той же подсистемы."""
    points = buildings_for_map(subsystem)
    if include_geo_objects:
        for g in geo_objects_for_map(subsystem):
            points.append(
                {
                    "id": g["id"],
                    "kind": "geo",
                    "title": g["title"],
                    "address": g.get("address") or "",
                    "lat": g["lat"],
                    "lng": g["lng"],
                    "color": g.get("color") or "#00cfe8",
                    "layer": g.get("layer") or "",
                    "case_id": g.get("case_id"),
                }
            )
    return points


def map_center_for_points(points: list[dict]) -> tuple[float, float]:
    if not points:
        return DEFAULT_CENTER
    lat = sum(p["lat"] for p in points) / len(points)
    lng = sum(p["lng"] for p in points) / len(points)
    return (lat, lng)


def geocode_address(address: str) -> tuple[Decimal, Decimal]:
    """
    Геокодирование: DaData (geo_lat/lon) → Яндекс HTTP Геокодер → демо (M67).
    """
    address = (address or "").strip()
    if not address:
        return demo_geocode("")

    from delayu.services.dadata import geocode_from_address, is_configured

    if is_configured():
        lat, lng = geocode_from_address(address)
        if lat is not None and lng is not None:
            return lat, lng

    api_key = getattr(settings, "YANDEX_MAPS_API_KEY", "")
    if not api_key:
        return demo_geocode(address)

    params = urllib.parse.urlencode(
        {
            "apikey": api_key,
            "format": "json",
            "geocode": address,
            "results": 1,
        }
    )
    url = f"https://geocode-maps.yandex.ru/1.x/?{params}"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        members = (
            data.get("response", {})
            .get("GeoObjectCollection", {})
            .get("featureMember", [])
        )
        if not members:
            return demo_geocode(address)
        pos = members[0]["GeoObject"]["Point"]["pos"]
        lng_s, lat_s = pos.split()
        return Decimal(lat_s), Decimal(lng_s)
    except (urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError):
        return demo_geocode(address)
