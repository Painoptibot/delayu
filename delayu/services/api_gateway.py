"""M43 — аутентификация API-ключами и rate limiting."""
from __future__ import annotations

import hashlib
from functools import wraps

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone

from delayu.models import ApiClientKey


class ApiGatewayError(Exception):
    def __init__(self, code: str, message: str, status: int = 401):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


def extract_api_key(request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Api-Key") or request.GET.get("api_key") or "").strip()


def verify_api_key(raw: str) -> ApiClientKey | None:
    if not raw or len(raw) < 16:
        return None
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    prefix = raw[:12]
    return (
        ApiClientKey.objects.filter(
            key_hash=key_hash,
            key_prefix=prefix,
            is_active=True,
        )
        .select_related("subsystem")
        .first()
    )


def check_rate_limit(api_key: ApiClientKey) -> None:
    hour = timezone.now().strftime("%Y%m%d%H")
    cache_key = f"delayu:api_rate:{api_key.pk}:{hour}"
    count = cache.get(cache_key, 0)
    if count >= api_key.rate_limit_per_hour:
        raise ApiGatewayError(
            "rate_limit_exceeded",
            f"Лимит {api_key.rate_limit_per_hour} запросов/час исчерпан",
            status=429,
        )
    cache.set(cache_key, count + 1, timeout=3700)


def touch_api_key(api_key: ApiClientKey) -> None:
    ApiClientKey.objects.filter(pk=api_key.pk).update(last_used_at=timezone.now())


def resolve_api_context(request):
    """Возвращает (user, api_key, subsystem) или raises ApiGatewayError."""
    raw = extract_api_key(request)
    if raw:
        api_key = verify_api_key(raw)
        if not api_key:
            raise ApiGatewayError("invalid_api_key", "Недействительный API-ключ")
        check_rate_limit(api_key)
        touch_api_key(api_key)
        return None, api_key, api_key.subsystem

    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        if user.is_superuser:
            from delayu.models import Subsystem

            sub = Subsystem.objects.order_by("pk").first()
            if sub:
                return user, None, sub
        from delayu.menu import get_active_membership

        membership = get_active_membership(user)
        if membership:
            return user, None, membership.subsystem
    raise ApiGatewayError("unauthorized", "Требуется сессия или API-ключ", status=401)


def api_access(*, module_code: str = "M43", action: str = "view", public: bool = False):
    """Декоратор для /api/v1/* — сессия или Bearer API key."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if public:
                return view_func(request, *args, **kwargs)
            try:
                user, api_key, subsystem = resolve_api_context(request)
            except ApiGatewayError as exc:
                return JsonResponse({"error": exc.code, "message": exc.message}, status=exc.status)
            if api_key is None and user is not None:
                from delayu.services.access import user_can

                if not user_can(user, module_code, action):
                    return JsonResponse({"error": "forbidden"}, status=403)
            request.api_user = user
            request.api_key = api_key
            request.api_subsystem = subsystem
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
