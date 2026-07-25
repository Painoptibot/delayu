"""Reverse proxy helpers for Odysseus (M87)."""
from __future__ import annotations

from urllib.parse import urljoin

import httpx
from django.http import HttpResponse, StreamingHttpResponse

from delayu.models_odysseus import OdysseusSettings

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "content-encoding",
    "content-length",
}


def path_allowed(cfg: OdysseusSettings, path: str) -> bool:
    normalized = "/" + (path or "").lstrip("/")
    if normalized != "/" and normalized.endswith("/"):
        normalized = normalized.rstrip("/") or "/"
    prefixes = cfg.get_allowed_path_prefixes()
    for prefix in prefixes:
        p = prefix if prefix.startswith("/") else f"/{prefix}"
        if p == "/":
            return True
        p_clean = p.rstrip("/") or "/"
        if normalized == p_clean or normalized.startswith(p_clean + "/"):
            return True
        if p.endswith("/") and normalized.startswith(p):
            return True
    return False


def build_upstream_url(cfg: OdysseusSettings, path: str, query: str = "") -> str:
    base = cfg.base_url.rstrip("/") + "/"
    rel = (path or "").lstrip("/")
    url = urljoin(base, rel)
    if query:
        url = f"{url}?{query}"
    return url


def proxy_request(request, *, cfg: OdysseusSettings, path: str):
    if not path_allowed(cfg, path):
        raise PermissionError("path not allowlisted")

    upstream = build_upstream_url(cfg, path, request.META.get("QUERY_STRING", ""))
    headers = {}
    for key, value in request.headers.items():
        lk = key.lower()
        if lk in HOP_BY_HOP or lk == "host":
            continue
        headers[key] = value
    if cfg.auth_mode == OdysseusSettings.AuthMode.HEADER_BRIDGE:
        headers["X-Delayu-User"] = request.user.get_username()
        headers["X-Delayu-Subsystem"] = str(cfg.subsystem_id)
    if cfg.auth_mode == OdysseusSettings.AuthMode.SHARED_SECRET and cfg.shared_secret:
        headers["X-Delayu-Secret"] = cfg.shared_secret

    method = request.method.upper()
    body = request.body if method in {"POST", "PUT", "PATCH"} else None
    timeout = cfg.timeout_s or 30

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        upstream_resp = client.request(method, upstream, headers=headers, content=body)

    excluded = {h for h in HOP_BY_HOP} | {"content-type"}
    response_headers = {
        k: v for k, v in upstream_resp.headers.items() if k.lower() not in excluded
    }
    content_type = upstream_resp.headers.get("content-type", "application/octet-stream")
    return HttpResponse(
        upstream_resp.content,
        status=upstream_resp.status_code,
        content_type=content_type,
        headers=response_headers,
    )
