"""Серверное маскирование ПДн (волна 1 #11–12)."""
from delayu.services.access import user_can

PII_PROFILE_KEYS = frozenset(
    {
        "phone",
        "phone_mobile",
        "phone_work",
        "phone_internal",
        "email_personal",
        "telegram",
        "address_registration",
        "address_residence",
        "middle_name",
        "snils",
        "inn",
        "passport_series",
        "passport_number",
        "passport_issued_by",
        "birth_date",
        "employee_number",
        "tab_number",
        "manager_name",
        "comment",
    }
)

PII_USER_KEYS = frozenset({"first_name", "last_name", "email"})


def user_may_view_pii(user, request=None) -> bool:
    if request and getattr(request, "session", None) and request.session.get("privacy_mode"):
        return False
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user_can(user, "M03", "view_pii") or user_can(user, "M02", "view_pii")


def set_privacy_mode(request, enabled: bool) -> None:
    request.session["privacy_mode"] = bool(enabled)
    request.session.modified = True


def privacy_mode_active(request) -> bool:
    return bool(getattr(request, "session", None) and request.session.get("privacy_mode"))


def mask_value(value, visible: int = 0) -> str:
    if value is None or value == "":
        return ""
    s = str(value)
    if len(s) <= visible:
        return "•" * len(s)
    return s[:visible] + "•" * min(8, len(s) - visible)


def mask_profile_dict(data: dict, *, allow_pii: bool) -> dict:
    if allow_pii:
        return dict(data)
    out = dict(data)
    for key in PII_PROFILE_KEYS:
        if key in out and out[key]:
            out[key] = mask_value(out[key], 0)
    for key in PII_USER_KEYS:
        if key in out and out[key]:
            out[key] = mask_value(out[key], 1)
    return out


def mask_correspondence(corr, *, allow_pii: bool):
    if allow_pii:
        return corr
    corr.counterparty = mask_value(corr.counterparty, 1)
    return corr
