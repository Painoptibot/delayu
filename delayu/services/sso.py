"""SSO / OIDC / ЕСИА — демо-поток и production token exchange (#69)."""
from __future__ import annotations

import json
import secrets
from urllib import error, parse, request

from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class SsoError(Exception):
    pass


def active_sso_providers(*, subsystem=None):
    from delayu.models import SsoProvider

    qs = SsoProvider.objects.filter(is_active=True)
    if subsystem:
        qs = qs.filter(subsystem=subsystem)
    return qs.order_by("name")


def build_authorize_url(provider, request) -> str:
    """URL IdP или демо-callback для локальной отладки."""
    state = secrets.token_urlsafe(24)
    request.session["sso_state"] = state
    request.session["sso_provider_id"] = provider.pk
    meta = provider.metadata or {}
    if meta.get("demo"):
        params = urlencode({"code": "demo", "state": state})
        return request.build_absolute_uri(reverse("sso-callback")) + f"?{params}"
    auth_base = meta.get("authorization_endpoint") or meta.get("auth_url")
    if not auth_base:
        raise SsoError("Не задан authorization_endpoint в metadata провайдера")
    redirect_uri = request.build_absolute_uri(reverse("sso-callback"))
    query = urlencode(
        {
            "client_id": provider.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
            "scope": meta.get("scope", "openid profile email"),
        }
    )
    sep = "&" if "?" in auth_base else "?"
    return f"{auth_base}{sep}{query}"


def validate_callback(request) -> tuple:
    state = request.GET.get("state", "")
    if not state or state != request.session.get("sso_state"):
        raise SsoError("Неверный state SSO")
    provider_id = request.session.get("sso_provider_id")
    if not provider_id:
        raise SsoError("Сессия SSO не найдена")
    from delayu.models import SsoProvider

    provider = SsoProvider.objects.filter(pk=provider_id, is_active=True).first()
    if not provider:
        raise SsoError("Провайдер SSO недоступен")
    code = request.GET.get("code", "")
    if not code:
        raise SsoError("Код авторизации не получен")
    return provider, code


def _http_post_form(url: str, payload: dict, *, headers: dict | None = None) -> dict:
    data = parse.urlencode(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SsoError(f"OIDC token HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SsoError(f"OIDC token endpoint недоступен: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SsoError("OIDC token endpoint вернул не-JSON") from exc


def exchange_oidc_token(provider, code: str, redirect_uri: str) -> dict:
    meta = provider.metadata or {}
    token_url = meta.get("token_endpoint")
    if not token_url:
        raise SsoError("Не задан token_endpoint в metadata провайдера")
    client_secret = meta.get("client_secret", "")
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": provider.client_id,
    }
    if client_secret:
        payload["client_secret"] = client_secret
    return _http_post_form(token_url, payload)


def fetch_oidc_userinfo(provider, access_token: str) -> dict:
    meta = provider.metadata or {}
    userinfo_url = meta.get("userinfo_endpoint")
    if not userinfo_url:
        raise SsoError("Не задан userinfo_endpoint в metadata провайдера")
    req = request.Request(userinfo_url, method="GET")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Accept", "application/json")
    try:
        with request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SsoError(f"OIDC userinfo HTTP {exc.code}: {detail}") from exc
    except error.URLError as exc:
        raise SsoError(f"OIDC userinfo недоступен: {exc.reason}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise SsoError("OIDC userinfo вернул не-JSON") from exc


def _map_user_from_claims(provider, claims: dict):
    meta = provider.metadata or {}
    username_field = meta.get("username_claim", "preferred_username")
    username = (
        claims.get(username_field)
        or claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
    )
    if not username:
        raise SsoError("OIDC userinfo не содержит идентификатор пользователя")
    username = str(username).strip()[:150]
    user = User.objects.filter(username=username, is_active=True).first()
    if not user and meta.get("auto_provision"):
        user = User.objects.create_user(username=username, password=secrets.token_urlsafe(32))
    if not user:
        raise SsoError(f"Пользователь {username} не найден (auto_provision выключен)")
    return user


def resolve_sso_user(provider, code: str, *, redirect_uri: str | None = None):
    """Демо: code=demo → пользователь из metadata; production — обмен code на token."""
    meta = provider.metadata or {}
    if code == "demo" or meta.get("demo"):
        username = meta.get("demo_username") or "admin"
        user = User.objects.filter(username=username, is_active=True).first()
        if not user:
            raise SsoError(f"Демо-пользователь {username} не найден")
        return user, {"mode": "demo", "provider": provider.name}
    if not redirect_uri:
        raise SsoError("redirect_uri обязателен для production OIDC")
    tokens = exchange_oidc_token(provider, code, redirect_uri)
    access_token = tokens.get("access_token")
    if not access_token:
        raise SsoError("OIDC token response без access_token")
    claims = fetch_oidc_userinfo(provider, access_token)
    user = _map_user_from_claims(provider, claims)
    return user, {
        "mode": "oidc",
        "provider": provider.name,
        "sub": claims.get("sub", ""),
    }


def urlencode(params: dict) -> str:
    return parse.urlencode(params)
