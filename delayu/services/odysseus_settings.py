"""Odysseus settings helpers (M87)."""
from __future__ import annotations

from django.utils import timezone

from delayu.models_odysseus import OdysseusSettings


def ensure_odysseus_settings(subsystem) -> OdysseusSettings:
    cfg, _ = OdysseusSettings.objects.get_or_create(
        subsystem=subsystem,
        defaults={
            "enabled": False,
            "base_url": "http://127.0.0.1:7000",
            "embed_mode": OdysseusSettings.EmbedMode.PROXY_SHELL,
            "upstream_url": "https://github.com/odysseus-dev/odysseus.git",
            "vendor_path": "vendor/odysseus",
            "auth_mode": OdysseusSettings.AuthMode.NONE_DEV,
            "allowed_path_prefixes": ["/", "/api/", "/assets/", "/static/"],
            "role_allowlist": ["invest_admin", "invest_dept"],
            "timeout_s": 30,
            "options": {},
        },
    )
    return cfg


def check_odysseus_health(cfg: OdysseusSettings) -> bool:
    """Probe upstream base_url; persist last_health_* on cfg."""
    import httpx

    ok = False
    try:
        with httpx.Client(timeout=min(cfg.timeout_s or 30, 10), follow_redirects=True) as client:
            resp = client.get(cfg.base_url.rstrip("/") + "/")
            ok = resp.status_code < 500
    except Exception:
        ok = False
    cfg.last_health_ok = ok
    cfg.last_health_at = timezone.now()
    cfg.save(update_fields=["last_health_ok", "last_health_at", "updated_at"])
    return ok
