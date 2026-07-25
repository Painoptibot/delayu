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
