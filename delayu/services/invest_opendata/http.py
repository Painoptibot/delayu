"""HTTP helpers for open-data live mode (allowlisted hosts only)."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class OpenDataHttpError(Exception):
    pass


def _allowlist() -> set[str]:
    raw = getattr(settings, "INVEST_OPENDATA_ALLOWLIST", []) or []
    return {str(h).strip().lower() for h in raw if str(h).strip()}


def host_allowed(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    allowed = _allowlist()
    if host in allowed:
        return True
    return any(host.endswith("." + a) for a in allowed if a)


def opendata_get(url: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
    if not host_allowed(url):
        raise OpenDataHttpError(f"Host not allowlisted: {urlparse(url).hostname}")
    timeout = float(getattr(settings, "INVEST_OPENDATA_TIMEOUT", 8))
    headers = {
        "User-Agent": str(
            getattr(settings, "INVEST_OPENDATA_USER_AGENT", "DelayuInvestOpenData/1.0")
        ),
        "Accept": "application/json, text/html, */*",
    }
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        resp = client.get(url, params=params)
        return resp
