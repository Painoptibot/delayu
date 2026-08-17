"""Yandex Maps integrations used by invest and public map screens."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)

GEOCODER_URL = "https://geocode-maps.yandex.ru/1.x/"
ROUTER_URL = "https://api.routing.yandex.net/v2/route"


class YandexRouteError(Exception):
    """Raised when Yandex routing cannot return a drive path."""


class YandexGeocodeError(Exception):
    """Raised when Yandex geocoding cannot return coordinates."""


def _api_key() -> str:
    return (getattr(settings, "YANDEX_MAPS_API_KEY", "") or "").strip()


def geocode_address(address: str) -> tuple[Decimal, Decimal]:
    """Return (lat, lon) for an address via Yandex Geocoder HTTP API."""
    key = _api_key()
    if not key:
        raise YandexGeocodeError("Укажите YANDEX_MAPS_API_KEY")
    query = (address or "").strip()
    if not query:
        raise YandexGeocodeError("Укажите адрес для геокодирования.")

    params = urllib.parse.urlencode({"apikey": key, "format": "json", "geocode": query, "results": 1})
    url = f"{GEOCODER_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        logger.warning("Yandex geocoder HTTP %s: %s", exc.code, body)
        raise YandexGeocodeError("Геокодер Яндекса вернул ошибку.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Yandex geocoder request failed: %s", exc)
        raise YandexGeocodeError("Геокодер Яндекса недоступен.") from exc

    members = (
        payload.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])
    )
    if not members:
        raise YandexGeocodeError("Геокодер Яндекса не нашёл координаты.")
    pos = members[0].get("GeoObject", {}).get("Point", {}).get("pos", "")
    parts = pos.split()
    if len(parts) != 2:
        raise YandexGeocodeError("Геокодер Яндекса вернул координаты в неизвестном формате.")
    lon, lat = parts
    try:
        return Decimal(lat), Decimal(lon)
    except Exception as exc:
        raise YandexGeocodeError("Геокодер Яндекса вернул некорректные координаты.") from exc


def route_drive(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> dict:
    """Автомаршрут через HTTP Router API. Возвращает метры, секунды и полилинию [lat, lon]."""
    key = _api_key()
    if not key:
        raise YandexRouteError("Укажите YANDEX_MAPS_API_KEY")
    params = urllib.parse.urlencode(
        {
            "apikey": key,
            "waypoints": f"{from_lat},{from_lon}|{to_lat},{to_lon}",
            "mode": "driving",
        }
    )
    url = f"{ROUTER_URL}?{params}"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        logger.info("Yandex router HTTP %s: %s", exc.code, body)
        raise YandexRouteError("Маршрутизатор Яндекса вернул ошибку.") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.info("Yandex router request failed: %s", exc)
        raise YandexRouteError("Маршрутизатор Яндекса недоступен.") from exc

    parsed = _parse_router_payload(payload)
    if not parsed:
        raise YandexRouteError("Маршрутизатор Яндекса вернул пустой маршрут.")
    return parsed


def _parse_router_payload(payload: dict) -> dict | None:
    """Разбор нескольких форматов Router API."""
    route = payload.get("route") or payload.get("routes") or payload
    if isinstance(route, list) and route:
        route = route[0]
    if not isinstance(route, dict):
        return None

    meters = 0
    seconds = 0
    points: list[list[float]] = []
    steps_out: list[dict] = []

    legs = route.get("legs") or []
    if not legs and route.get("steps"):
        legs = [route]

    for leg in legs:
        for step in leg.get("steps") or []:
            meters += int(step.get("length") or step.get("distance") or 0)
            seconds += int(step.get("duration") or 0)
            street = (step.get("street") or step.get("name") or "").strip()
            if street:
                steps_out.append({"text": street, "meters": int(step.get("length") or 0)})
            poly = step.get("polyline") or {}
            raw_pts = poly.get("points") or poly.get("coordinates") or []
            for pt in raw_pts:
                if isinstance(pt, (list, tuple)) and len(pt) >= 2:
                    # Router часто отдаёт lon, lat
                    a, b = float(pt[0]), float(pt[1])
                    if abs(a) > 90:
                        points.append([b, a])
                    else:
                        points.append([a, b])

    if not meters:
        meters = int(route.get("distance") or route.get("length") or 0)
    if not seconds:
        seconds = int(route.get("duration") or 0)
    if meters <= 0:
        return None
    return {
        "engine": "yandex",
        "distance_m": meters,
        "duration_s": seconds,
        "polyline": points,
        "steps": steps_out[:12],
    }
