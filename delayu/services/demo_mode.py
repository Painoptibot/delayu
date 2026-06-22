"""#6 — режим демонстрации реестра (read-only мутации)."""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages


def global_demo_enabled() -> bool:
    return getattr(settings, "DELAYU_DEMO_MODE", False)


def subsystem_demo_enabled(subsystem) -> bool:
    if not subsystem:
        return False
    try:
        return bool(subsystem.pii_policy.demo_mode)
    except Exception:
        return False


def is_demo_mode(request) -> bool:
    user = getattr(request, "user", None)
    if user and user.is_authenticated and user.is_superuser:
        return False
    if global_demo_enabled():
        return True
    from delayu.menu import get_active_membership

    m = get_active_membership(request.user) if getattr(request, "user", None) and request.user.is_authenticated else None
    return subsystem_demo_enabled(m.subsystem if m else None)


_BLOCKED_PREFIXES = (
    "/archive/cases/purge-expired/",
    "/administration/audit/snapshot/",
    "/ops/bulk/",
    "/cases/bulk/",
    "/uzhv/bulk/",
)

_BLOCKED_SUFFIXES = (
    "/delete/",
    "/purge-expired/",
)


def blocks_mutation(request) -> bool:
    if not is_demo_mode(request):
        return False
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return False
    path = request.path
    if any(path.startswith(p) for p in _BLOCKED_PREFIXES):
        return True
    if any(path.endswith(s) for s in _BLOCKED_SUFFIXES):
        return True
    if "/purge-expired/" in path:
        return True
    return False


def deny_if_demo(request):
    if blocks_mutation(request):
        messages.warning(request, "Режим демо: изменение данных отключено.")
        return True
    return False
