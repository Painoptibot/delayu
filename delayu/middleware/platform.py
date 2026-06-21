"""Middleware платформы: correlation id, membership, security audit."""
import logging
import uuid

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

logger = logging.getLogger("delayu.request")

SKIP_MEMBERSHIP_PREFIXES = (
    "/auth/",
    "/static/",
    "/media/",
    "/admin/",
    "/api/v1/health/",
    "/docs/tz/",
)

TWO_FACTOR_SKIP_PREFIXES = (
    "/auth/",
    "/static/",
    "/media/",
    "/admin/",
    "/api/v1/health/",
    "/docs/tz/",
)


class CorrelationIdMiddleware:
    """Structured logging: correlation_id на каждый запрос (#28)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.correlation_id = cid
        response = self.get_response(request)
        response["X-Correlation-ID"] = cid
        if hasattr(request, "user") and request.user.is_authenticated:
            logger.info(
                "request",
                extra={
                    "correlation_id": cid,
                    "path": request.path,
                    "method": request.method,
                    "user_id": request.user.pk,
                    "status": response.status_code,
                },
            )
        return response


class ActiveMembershipMiddleware:
    """Отклоняет платформенные запросы без активной подсистемы (#2)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in SKIP_MEMBERSHIP_PREFIXES):
            return self.get_response(request)
        if not getattr(request, "user", None) or not request.user.is_authenticated:
            return self.get_response(request)
        from delayu.services.scope import is_platform_admin, path_requires_platform_admin

        if path_requires_platform_admin(path) and not is_platform_admin(request.user):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied("Раздел доступен только администратору платформы")
        if request.user.is_superuser:
            return self.get_response(request)
        from delayu.menu import get_active_membership

        if get_active_membership(request.user):
            return self.get_response(request)
        if path in ("/", reverse("platform-home")):
            return self.get_response(request)
        if path.startswith("/api/") and request.headers.get("Accept", "").startswith("application/json"):
            return JsonResponse({"error": "no_membership"}, status=403)
        return redirect("platform-home")


class TwoFactorMiddleware:
    """Проверка TOTP после входа (#13–14)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in TWO_FACTOR_SKIP_PREFIXES):
            return self.get_response(request)
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return self.get_response(request)
        from delayu.services.security_policy import profile_for, requires_2fa
        from delayu.services.totp import profile_totp_enabled

        profile = profile_for(user)
        if profile_totp_enabled(profile) and not request.session.get("2fa_verified"):
            verify_url = reverse("two-factor-verify")
            if not path.startswith(verify_url) and path != reverse("logout"):
                return redirect(f"{verify_url}?next={path}")
        elif requires_2fa(user) and not profile_totp_enabled(profile):
            setup_url = reverse("two-factor-setup")
            allowed = (
                path.startswith(setup_url)
                or path.startswith(reverse("platform-cabinet-security"))
                or path == reverse("logout")
            )
            if not allowed:
                return redirect("two-factor-setup")
        return self.get_response(request)


class SessionRegistryMiddleware:
    """Журнал сессий и отзыв (#14)."""

    SKIP_PREFIXES = (
        "/static/",
        "/media/",
        "/admin/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if not any(path.startswith(p) for p in self.SKIP_PREFIXES):
            user = getattr(request, "user", None)
            if user and user.is_authenticated:
                from delayu.services.session_registry import is_session_revoked, touch_session

                key = request.session.session_key
                if key and is_session_revoked(key):
                    from django.contrib.auth import logout

                    logout(request)
                    return redirect(reverse("login"))
                touch_session(request)
        return self.get_response(request)


class DemoModeMiddleware:
    """#6 — блокирует мутации в режиме демонстрации."""

    SKIP_PREFIXES = (
        "/auth/",
        "/static/",
        "/media/",
        "/admin/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)
        from delayu.services.demo_mode import blocks_mutation, deny_if_demo

        if blocks_mutation(request):
            deny_if_demo(request)
            from django.http import HttpResponseForbidden

            return HttpResponseForbidden("Режим демо: изменение данных отключено.")
        return self.get_response(request)


class PrivacyModeAuditMiddleware:
    """Журнал включения режима конфиденциальности (#11)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and "/platform/privacy-mode/" in request.path:
            from delayu.menu import get_active_membership
            from delayu.services.events import record_event

            m = get_active_membership(request.user) if request.user.is_authenticated else None
            enabled = request.POST.get("enabled") == "1"
            if m:
                record_event(
                    subsystem=m.subsystem,
                    actor=request.user,
                    action="privacy_mode.toggle",
                    payload={"enabled": enabled},
                    request=request,
                    description="Режим скрытия ПДн",
                )
        return self.get_response(request)
