# -*- coding: utf-8 -*-
"""Сервисы агрегации статусов АЗС ЮФО."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any
import json
import logging
import urllib.error
import urllib.request

from django.db.models import Count
from django.utils import timezone

from delayu.models_fuel_ufo import (
    FuelUfoAvailability,
    FuelUfoAzsPoint,
    FuelUfoDataSource,
    FuelUfoSnapshot,
    FuelUfoSourceObservation,
    FuelUfoUserReport,
    point_in_ufo,
)

# TTL по источникам
SOURCE_TTL = {
    FuelUfoDataSource.CITY_HQ: timedelta(hours=6),
    FuelUfoDataSource.AZS_OPERATOR: timedelta(hours=2),
    FuelUfoDataSource.SBER: timedelta(minutes=45),
    FuelUfoDataSource.TBANK: timedelta(minutes=45),
    FuelUfoDataSource.USER: timedelta(minutes=90),
    FuelUfoDataSource.MANUAL: timedelta(hours=12),
}

SOURCE_PRIORITY = {
    FuelUfoDataSource.CITY_HQ: 100,
    FuelUfoDataSource.AZS_OPERATOR: 90,
    FuelUfoDataSource.SBER: 70,
    FuelUfoDataSource.TBANK: 70,
    FuelUfoDataSource.USER: 40,
    FuelUfoDataSource.MANUAL: 60,
}

USER_CLUSTER_MIN = 2
logger = logging.getLogger(__name__)
OSRM_URL = "https://router.project-osrm.org/route/v1/driving/{from_lon},{from_lat};{to_lon},{to_lat}"


def ensure_in_ufo(lat: float, lon: float) -> None:
    if not point_in_ufo(lat, lon):
        raise ValueError("Точка вне ЮФО")


def _fresh_obs(azs: FuelUfoAzsPoint, grade: str) -> list[FuelUfoSourceObservation]:
    now = timezone.now()
    out: list[FuelUfoSourceObservation] = []
    for obs in azs.observations.filter(fuel_grade=grade).order_by("-observed_at")[:40]:
        ttl = SOURCE_TTL.get(obs.source, timedelta(hours=1))
        if now - obs.observed_at <= ttl:
            out.append(obs)
    return out


def _pick_status(obs_list: list[FuelUfoSourceObservation]) -> tuple[str, str, float, Any]:
    if not obs_list:
        return FuelUfoAvailability.UNKNOWN, "", 0.0, None

    # user cluster
    user_obs = [o for o in obs_list if o.source == FuelUfoDataSource.USER]
    if len(user_obs) >= USER_CLUSTER_MIN:
        tallies: dict[str, int] = {}
        for o in user_obs[:10]:
            tallies[o.availability] = tallies.get(o.availability, 0) + 1
        best_av = max(tallies, key=tallies.get)
        if tallies[best_av] >= USER_CLUSTER_MIN:
            latest = max(user_obs, key=lambda x: x.observed_at)
            return best_av, FuelUfoDataSource.USER, 0.55 + 0.05 * tallies[best_av], latest.observed_at

    ranked = sorted(
        obs_list,
        key=lambda o: (SOURCE_PRIORITY.get(o.source, 0), o.observed_at),
        reverse=True,
    )
    top = ranked[0]
    return top.availability, top.source, float(top.confidence), top.observed_at


def recompute_snapshot(azs: FuelUfoAzsPoint) -> FuelUfoSnapshot:
    snap, _ = FuelUfoSnapshot.objects.get_or_create(azs=azs)
    sources_meta: dict[str, Any] = {}
    best_source = ""
    best_conf = 0.0
    last_at = None
    queue = None

    for grade, field in (
        ("ai92", "status_ai92"),
        ("ai95", "status_ai95"),
        ("diesel", "status_diesel"),
    ):
        status, source, conf, observed = _pick_status(_fresh_obs(azs, grade))
        setattr(snap, field, status)
        sources_meta[grade] = {
            "status": status,
            "source": source,
            "confidence": round(conf, 3),
            "observed_at": observed.isoformat() if observed else None,
        }
        if conf >= best_conf and source:
            best_conf = conf
            best_source = source
            last_at = observed

    # очередь из свежих наблюдений
    for obs in azs.observations.order_by("-observed_at")[:15]:
        ttl = SOURCE_TTL.get(obs.source, timedelta(hours=1))
        if timezone.now() - obs.observed_at <= ttl and obs.queue_minutes is not None:
            queue = obs.queue_minutes
            break

    snap.primary_source = best_source
    snap.confidence = best_conf
    snap.last_reliable_at = last_at
    snap.queue_minutes = queue
    snap.sources_json = sources_meta
    snap.save()
    return snap


def local_day_start(now=None):
    now = timezone.localtime(now or timezone.now())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def user_report_quota(*, phone: str = "") -> dict[str, Any]:
    """Одна отметка наличия на человека в календарные сутки (Europe/Moscow)."""
    if not phone:
        return {
            "can_report": False,
            "reason": "auth_required",
            "detail": "Войдите, чтобы отметить наличие. Один раз в сутки — по своей АЗС.",
            "reported_today": None,
            "next_at": None,
        }
    start = local_day_start()
    last = (
        FuelUfoUserReport.objects.filter(phone=phone, created_at__gte=start)
        .select_related("azs")
        .order_by("-created_at")
        .first()
    )
    if last:
        next_at = start + timedelta(days=1)
        return {
            "can_report": False,
            "reason": "already_today",
            "detail": f"Сегодня вы уже отметили «{last.azs.name}». Следующая отметка завтра.",
            "reported_today": {
                "azs_id": last.azs_id,
                "azs_name": last.azs.name,
                "availability": last.availability,
                "created_at": last.created_at.isoformat(),
            },
            "next_at": next_at.isoformat(),
        }
    return {
        "can_report": True,
        "reason": "ok",
        "detail": "",
        "reported_today": None,
        "next_at": (start + timedelta(days=1)).isoformat(),
    }


def add_user_report(
    *,
    azs: FuelUfoAzsPoint,
    device_id: str,
    availability: str,
    fuel_grade: str = "ai95",
    queue_minutes: int | None = None,
    limit_liters: int | None = None,
    cans_allowed: bool | None = None,
    comment: str = "",
    phone: str = "",
    lat: float | None = None,
    lon: float | None = None,
) -> FuelUfoUserReport:
    phone = (phone or "").strip()
    if not phone:
        raise PermissionError("Войдите, чтобы отметить наличие")
    quota = user_report_quota(phone=phone)
    if not quota["can_report"]:
        raise PermissionError(quota["detail"] or "Сегодня отметка уже есть")

    confidence = 0.35
    if lat is not None and lon is not None:
        dist = haversine_m(float(lat), float(lon), float(azs.latitude), float(azs.longitude))
        if dist <= 400:
            confidence = 0.55
        elif dist <= 1500:
            confidence = 0.4

    report = FuelUfoUserReport.objects.create(
        azs=azs,
        device_id=(device_id or "")[:64],
        phone=phone[:16],
        availability=availability,
        fuel_grade=fuel_grade,
        queue_minutes=queue_minutes,
        limit_liters=limit_liters,
        cans_allowed=cans_allowed,
        comment=(comment or "")[:500],
    )
    FuelUfoSourceObservation.objects.create(
        azs=azs,
        source=FuelUfoDataSource.USER,
        fuel_grade=fuel_grade,
        availability=availability,
        queue_minutes=queue_minutes,
        limit_liters=limit_liters,
        cans_allowed=cans_allowed,
        confidence=confidence,
        observed_at=timezone.now(),
        raw_note=(comment or "")[:200],
    )
    recompute_snapshot(azs)
    return report


def ingest_partner_mock(azs: FuelUfoAzsPoint, source: str, grade: str, availability: str) -> None:
    FuelUfoSourceObservation.objects.create(
        azs=azs,
        source=source,
        fuel_grade=grade,
        availability=availability,
        confidence=0.7,
        observed_at=timezone.now(),
        raw_note="mock partner feed",
    )
    recompute_snapshot(azs)


_STATUS_RU = {
    FuelUfoAvailability.OK: "Есть",
    FuelUfoAvailability.LOW: "Мало",
    FuelUfoAvailability.EMPTY: "Нет",
    FuelUfoAvailability.UNKNOWN: "Нет данных",
}

_SOURCE_RU = {
    FuelUfoDataSource.CITY_HQ: "Штаб города",
    FuelUfoDataSource.AZS_OPERATOR: "Сеть АЗС",
    FuelUfoDataSource.SBER: "Партнёрский сигнал",
    FuelUfoDataSource.TBANK: "Партнёрский сигнал",
    FuelUfoDataSource.USER: "Водители",
    FuelUfoDataSource.MANUAL: "Оператор",
    FuelUfoDataSource.YANDEX_TRAFFIC: "Пробки",
}


def freshness_label(dt) -> str:
    if not dt:
        return "давность неизвестна"
    delta = timezone.now() - dt
    mins = int(delta.total_seconds() // 60)
    if mins < 1:
        return "только что"
    if mins < 60:
        return f"{mins} мин назад"
    hours = mins // 60
    if hours < 24:
        return f"{hours} ч назад"
    days = hours // 24
    return f"{days} дн назад"


def status_ru(code: str) -> str:
    return _STATUS_RU.get(code, "Нет данных")


def list_networks(*, limit: int = 20) -> list[dict[str, Any]]:
    rows = (
        FuelUfoAzsPoint.objects.filter(is_active=True)
        .exclude(network="")
        .values("network")
        .annotate(count=Count("id"))
        .order_by("-count", "network")[:limit]
    )
    return [{"name": r["network"], "count": r["count"]} for r in rows]


def serialize_azs(
    azs: FuelUfoAzsPoint,
    *,
    lite: bool = False,
    origin: tuple[float, float] | None = None,
) -> dict[str, Any]:
    snap = getattr(azs, "snapshot", None)
    if snap is None:
        try:
            snap = azs.snapshot
        except FuelUfoSnapshot.DoesNotExist:
            snap = recompute_snapshot(azs)

    status = {
        "ai92": snap.status_ai92,
        "ai95": snap.status_ai95,
        "diesel": snap.status_diesel,
    }
    rank = {"ok": 0, "low": 1, "unknown": 2, "empty": 3}
    best_grade = min(status.values(), key=lambda s: rank.get(s, 9))

    payload: dict[str, Any] = {
        "id": azs.id,
        "code": azs.code,
        "name": azs.name,
        "network": azs.network,
        "address": azs.address,
        "region": azs.region,
        "city": azs.city,
        "lat": float(azs.latitude),
        "lon": float(azs.longitude),
        "status": status,
        "status_labels": {k: status_ru(v) for k, v in status.items()},
        "freshness_label": freshness_label(snap.last_reliable_at),
        "freshness_minutes": (
            int((timezone.now() - snap.last_reliable_at).total_seconds() // 60)
            if snap.last_reliable_at
            else None
        ),
        "last_reliable_at": snap.last_reliable_at.isoformat() if snap.last_reliable_at else None,
        "best_availability": best_grade,
        "can_refuel": best_grade in (FuelUfoAvailability.OK, FuelUfoAvailability.LOW),
    }
    if origin:
        payload["distance_km"] = round(
            haversine_m(origin[0], origin[1], float(azs.latitude), float(azs.longitude)) / 1000.0,
            1,
        )
    if lite:
        return payload
    payload.update(
        {
            "primary_source": snap.primary_source,
            "primary_source_label": _SOURCE_RU.get(snap.primary_source or "", "—"),
            "confidence": snap.confidence,
            "queue_minutes": snap.queue_minutes,
            "traffic_jams": snap.traffic_jams,
            "traffic_fetched_at": snap.traffic_fetched_at.isoformat()
            if snap.traffic_fetched_at
            else None,
            "sources": _enrich_sources(snap.sources_json or {}),
            "updated_at": snap.updated_at.isoformat() if snap.updated_at else None,
        }
    )
    return payload


def pick_nearby_azs(
    qs,
    *,
    lat: float,
    lon: float,
    grade: str,
    only_available: bool,
    limit: int,
) -> list[FuelUfoAzsPoint]:
    """Ближайшие АЗС, приоритет у станций с топливом."""
    grade = grade if grade in ("ai92", "ai95", "diesel") else "ai95"
    status_field = {
        "ai92": "snapshot__status_ai92",
        "ai95": "snapshot__status_ai95",
        "diesel": "snapshot__status_diesel",
    }[grade]
    rows = list(qs.values_list("id", "latitude", "longitude", status_field))
    scored: list[tuple[int, float, int]] = []
    for pk, alat, alon, st in rows:
        try:
            dist = haversine_m(lat, lon, float(alat), float(alon))
        except (TypeError, ValueError):
            continue
        st = st or FuelUfoAvailability.UNKNOWN
        if only_available and st not in (FuelUfoAvailability.OK, FuelUfoAvailability.LOW):
            continue
        has_fuel = 0 if st in (FuelUfoAvailability.OK, FuelUfoAvailability.LOW) else 1
        scored.append((has_fuel, dist, pk))
    scored.sort()
    fuel_n = max(8, limit - 4) if limit >= 8 else limit
    fuel_ids = [pk for has, _d, pk in scored if has == 0][:fuel_n]
    chosen = list(fuel_ids)
    for _has, _d, pk in scored:
        if len(chosen) >= limit:
            break
        if pk not in chosen:
            chosen.append(pk)
    objs = {a.id: a for a in qs.filter(id__in=chosen).select_related("snapshot")}
    return [objs[pk] for pk in chosen if pk in objs]


def _enrich_sources(sources: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for grade, meta in (sources or {}).items():
        if not isinstance(meta, dict):
            continue
        observed = meta.get("observed_at")
        observed_dt = None
        if observed:
            try:
                observed_dt = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
                if timezone.is_naive(observed_dt):
                    observed_dt = timezone.make_aware(observed_dt, dt_timezone.utc)
            except (TypeError, ValueError):
                observed_dt = None
        row = dict(meta)
        row["status_label"] = status_ru(meta.get("status") or "")
        row["source_label"] = _SOURCE_RU.get(meta.get("source") or "", "—")
        row["freshness_label"] = freshness_label(observed_dt) if observed_dt else "нет данных"
        out[grade] = row
    return out


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * atan2(sqrt(a), sqrt(1 - a))


def estimate_drive(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict[str, Any]:
    """Грубая оценка без геометрии: прямую на карте не рисуем."""
    straight = haversine_m(from_lat, from_lon, to_lat, to_lon)
    road_m = int(straight * 1.32)
    duration_s = max(90, int(road_m / 8.9))
    return {
        "engine": "estimate",
        "distance_m": road_m,
        "duration_s": duration_s,
        "polyline": [],
        "steps": [],
    }


def route_osrm(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict[str, Any]:
    """Дорожный путь по OpenStreetMap (OSRM) — запас, если у ключа Яндекса нет Router API."""
    url = OSRM_URL.format(
        from_lon=from_lon, from_lat=from_lat, to_lon=to_lon, to_lat=to_lat
    ) + "?overview=full&geometries=geojson&steps=true"
    req = urllib.request.Request(url, headers={"User-Agent": "fuel-ufo/1.0"})
    with urllib.request.urlopen(req, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("code") != "Ok" or not payload.get("routes"):
        raise ValueError("OSRM empty")
    route = payload["routes"][0]
    coords = (route.get("geometry") or {}).get("coordinates") or []
    polyline = []
    for pt in coords:
        if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            polyline.append([float(pt[1]), float(pt[0])])
    steps_out: list[dict[str, Any]] = []
    for leg in route.get("legs") or []:
        for step in leg.get("steps") or []:
            name = (step.get("name") or "").strip()
            maneuver = ((step.get("maneuver") or {}).get("modifier") or "")
            text = name or maneuver
            if text:
                steps_out.append({"text": text, "meters": int(step.get("distance") or 0)})
    if len(polyline) < 3:
        raise ValueError("OSRM too short")
    return {
        "engine": "osrm",
        "distance_m": int(route.get("distance") or 0),
        "duration_s": int(route.get("duration") or 0),
        "polyline": polyline,
        "steps": steps_out[:12],
    }


def format_route(route: dict[str, Any]) -> dict[str, Any]:
    meters = int(route.get("distance_m") or 0)
    seconds = int(route.get("duration_s") or 0)
    km = meters / 1000
    dist_text = f"{km:.1f} км" if km >= 1 else f"{meters} м"
    mins = max(1, int(round(seconds / 60)))
    if mins < 60:
        dur_text = f"{mins} мин"
    else:
        dur_text = f"{mins // 60} ч {mins % 60} мин"
    out = dict(route)
    out["distance_text"] = dist_text
    out["duration_text"] = dur_text
    return out


def build_drive_route(
    *,
    from_lat: float,
    from_lon: float,
    to_lat: float,
    to_lon: float,
) -> dict[str, Any]:
    if not (-90 <= from_lat <= 90 and -180 <= from_lon <= 180):
        raise ValueError("Некорректная точка отправления")
    ensure_in_ufo(to_lat, to_lon)
    from delayu.services.yandex_maps import YandexRouteError, route_drive

    try:
        return format_route(route_drive(from_lat, from_lon, to_lat, to_lon))
    except YandexRouteError:
        pass
    try:
        return format_route(route_osrm(from_lat, from_lon, to_lat, to_lon))
    except (ValueError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        logger.info("OSRM fallback failed: %s", exc)
        return format_route(estimate_drive(from_lat, from_lon, to_lat, to_lon))
