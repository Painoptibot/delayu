"""Безопасный redirect после входа (только существующие маршруты)."""
from __future__ import annotations

from urllib.parse import urlparse

from django.urls import Resolver404, resolve, reverse


def safe_next_url(request, raw: str | None, *, default_name: str = "platform-home") -> str:
    """Вернуть локальный URL для redirect(); неизвестные пути → главная."""
    fallback = reverse(default_name)
    if not raw or not str(raw).strip():
        return fallback

    raw = str(raw).strip()
    path = raw

    if raw.startswith(("http://", "https://")):
        parsed = urlparse(raw)
        host = request.get_host().split(":")[0]
        target_host = (parsed.netloc or "").split(":")[0]
        if target_host and target_host != host:
            return fallback
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
    elif not raw.startswith("/"):
        return fallback

    check_path = path.split("?", 1)[0] or "/"
    if check_path != "/" and not check_path.endswith("/"):
        try:
            resolve(check_path)
        except Resolver404:
            try:
                resolve(f"{check_path}/")
                path = f"{check_path}/" + (f"?{path.split('?', 1)[1]}" if "?" in path else "")
                check_path = f"{check_path}/"
            except Resolver404:
                return fallback

    try:
        resolve(check_path)
    except Resolver404:
        return fallback

    return path if path.startswith("/") else fallback
