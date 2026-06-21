"""Интеграция DaData: подсказки (suggest) и геокодирование адреса."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"

# Типы, доступные через прокси /api/v1/dadata/suggest/
SUGGEST_TYPES: dict[str, str] = {
    "address": f"{BASE_URL}/suggest/address",
    "fio": f"{BASE_URL}/suggest/fio",
    "party": f"{BASE_URL}/suggest/party",
    "email": f"{BASE_URL}/suggest/email",
    "phone": f"{BASE_URL}/suggest/phone",
    "passport": f"{BASE_URL}/suggest/passport",
    "fms_unit": f"{BASE_URL}/suggest/fms_unit",
    "bank": f"{BASE_URL}/suggest/bank",
    "country": f"{BASE_URL}/suggest/country",
}


def is_configured() -> bool:
    return bool(getattr(settings, "DADATA_API_KEY", "").strip())


def _headers() -> dict[str, str]:
    token = getattr(settings, "DADATA_API_KEY", "").strip()
    secret = getattr(settings, "DADATA_SECRET_KEY", "").strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {token}",
    }
    if secret:
        headers["X-Secret"] = secret
    return headers


def _post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        logger.warning("DaData HTTP %s: %s", exc.code, body)
        return {"suggestions": [], "error": f"http_{exc.code}"}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("DaData request failed: %s", exc)
        return {"suggestions": [], "error": "unavailable"}


def suggest(
    suggest_type: str,
    query: str,
    *,
    count: int = 10,
    extra: dict[str, Any] | None = None,
) -> dict:
    """
    Универсальный вызов подсказок DaData.
    extra: parts (для fio), locations (для address), status (для party), и т.д.
    """
    if not is_configured():
        return {"suggestions": [], "configured": False}
    url = SUGGEST_TYPES.get(suggest_type)
    if not url:
        return {"suggestions": [], "error": "unknown_type"}
    q = (query or "").strip()
    if len(q) < 1:
        return {"suggestions": []}
    payload: dict[str, Any] = {"query": q, "count": max(1, min(count, 20))}
    if extra:
        payload.update(extra)
    result = _post(url, payload)
    result["configured"] = True
    result["type"] = suggest_type
    return result


def geocode_from_address(address: str) -> tuple[Decimal | None, Decimal | None]:
    """Координаты из подсказки адреса (geo_lat / geo_lon)."""
    if not (address or "").strip():
        return None, None
    data = suggest("address", address, count=1)
    suggestions = data.get("suggestions") or []
    if not suggestions:
        return None, None
    geo = (suggestions[0].get("data") or {})
    lat = geo.get("geo_lat")
    lon = geo.get("geo_lon")
    if lat is None or lon is None:
        return None, None
    try:
        return Decimal(str(lat)), Decimal(str(lon))
    except Exception:
        return None, None


def integration_status() -> dict:
    """Краткий статус для шлюза интеграций."""
    return {
        "code": "dadata",
        "name": "DaData",
        "enabled": is_configured(),
        "hint": "Адрес, ФИО, телефон, e-mail, паспорт, организации, ФМС",
        "docs_url": "https://dadata.ru/api/",
    }
