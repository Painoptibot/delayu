"""ЕСИА для публичного портала «Топливный пропуск»."""
from __future__ import annotations

import secrets

from delayu.models import SsoProvider
from delayu.services.sso import SsoError, fetch_oidc_userinfo, exchange_oidc_token


def fuel_esia_providers(subsystem):
    return SsoProvider.objects.filter(
        subsystem=subsystem,
        is_active=True,
        provider_type=SsoProvider.ProviderType.ESIA,
    ).order_by("name")


def fuel_esia_provider_for_portal(subsystem):
    for provider in fuel_esia_providers(subsystem):
        meta = provider.metadata or {}
        if meta.get("fuel_citizen", True):
            return provider
    return None


def build_fuel_esia_url(provider, request) -> str:
    state = secrets.token_urlsafe(24)
    request.session["fuel_esia_state"] = state
    request.session["fuel_esia_provider_id"] = provider.pk
    root = getattr(request, "fuel_portal_root", "") or ""
    callback_path = root.rstrip("/") + "/auth/esia/callback/"
    callback_url = request.build_absolute_uri(callback_path)
    meta = provider.metadata or {}
    if meta.get("demo"):
        from delayu.services.sso import urlencode

        params = urlencode({"code": "demo", "state": state})
        return f"{callback_url}?{params}"
    # production: override redirect in build_authorize_url — use standard SSO with fuel callback
    request.session["sso_state"] = state
    request.session["sso_provider_id"] = provider.pk
    meta = provider.metadata or {}
    auth_base = meta.get("authorization_endpoint") or meta.get("auth_url")
    if not auth_base:
        raise SsoError("Не задан authorization_endpoint в metadata провайдера")
    from delayu.services.sso import urlencode

    query = urlencode(
        {
            "client_id": provider.client_id,
            "response_type": "code",
            "redirect_uri": callback_url,
            "state": state,
            "scope": meta.get("scope", "openid profile email phone"),
        }
    )
    sep = "&" if "?" in auth_base else "?"
    return f"{auth_base}{sep}{query}"


def validate_fuel_esia_callback(request) -> tuple[SsoProvider, str]:
    state = request.GET.get("state", "")
    if not state or state != request.session.get("fuel_esia_state"):
        raise SsoError("Неверный state ЕСИА")
    provider_id = request.session.get("fuel_esia_provider_id")
    if not provider_id:
        raise SsoError("Сессия ЕСИА не найдена")
    provider = SsoProvider.objects.filter(pk=provider_id, is_active=True).first()
    if not provider:
        raise SsoError("Провайдер ЕСИА недоступен")
    code = request.GET.get("code", "")
    if not code:
        raise SsoError("Код авторизации не получен")
    return provider, code


def resolve_fuel_esia_identity(provider, code: str, *, redirect_uri: str) -> dict:
    """Идентификация гражданина из ЕСИА (демо или OIDC)."""
    meta = provider.metadata or {}
    if code == "demo" or meta.get("demo"):
        return {
            "esia_oid": meta.get("demo_sub") or "esia-demo-001",
            "full_name": meta.get("demo_name") or "Иванов Иван Иванович",
            "phone": meta.get("demo_phone") or "79001234567",
        }
    tokens = exchange_oidc_token(provider, code, redirect_uri)
    access_token = tokens.get("access_token")
    if not access_token:
        raise SsoError("OIDC token response без access_token")
    claims = fetch_oidc_userinfo(provider, access_token)
    phone = (
        claims.get("phone")
        or claims.get("mobile")
        or claims.get("phone_number")
        or ""
    )
    name = claims.get("name") or claims.get("full_name") or ""
    if not name:
        parts = [claims.get("family_name"), claims.get("given_name"), claims.get("middle_name")]
        name = " ".join(p for p in parts if p)
    return {
        "esia_oid": str(claims.get("sub") or ""),
        "full_name": str(name).strip(),
        "phone": str(phone).strip(),
    }
