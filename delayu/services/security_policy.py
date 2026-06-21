"""Политики безопасности: 2FA, пароли, сессии (#13–14)."""
from django.contrib.auth import get_user_model

User = get_user_model()

PII_ROLE_CODES = frozenset({"admin", "security", "hr", "operator"})


def profile_for(user):
    return getattr(user, "delayu_profile", None)


def requires_2fa(user) -> bool:
    if not user.is_authenticated or user.is_superuser:
        return False
    from delayu.menu import get_active_membership

    m = get_active_membership(user)
    if not m:
        return False
    role_code = (m.role.code or "").lower()
    if role_code in PII_ROLE_CODES:
        return True
    from delayu.services.access import user_can

    return user_can(user, "M03", "view_pii")


def check_login_allowed(user) -> tuple[bool, str]:
    prof = profile_for(user)
    if prof and prof.must_change_password:
        return True, "must_change_password"
    if requires_2fa(user) and prof and not prof.two_factor_enabled:
        return True, "2fa_required"
    return True, "ok"


def log_failed_login(username: str, request=None):
    from delayu.models import AuditLog

    ip = request.META.get("REMOTE_ADDR") if request else None
    AuditLog.objects.create(
        user=None,
        subsystem=None,
        action="security.login_failed",
        model_name="User",
        object_id=username[:64],
        payload={"username": username},
        ip_address=ip,
    )
