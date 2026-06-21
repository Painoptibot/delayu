"""#10 — фильтрация данных по организации membership."""
from __future__ import annotations

from delayu.menu import get_active_membership

_ORG_WIDE_ROLES = frozenset({"admin", "director", "auditor"})


def apply_organization_scope(user, subsystem, qs):
    """Ограничить queryset делами организации пользователя (кроме широких ролей)."""
    if not user or not getattr(user, "is_authenticated", False) or user.is_superuser:
        return qs
    membership = get_active_membership(user)
    if not membership or membership.subsystem_id != subsystem.pk:
        return qs.none()
    role_code = (membership.role.code or "").lower()
    if role_code in _ORG_WIDE_ROLES:
        return qs
    if membership.organization_id:
        return qs.filter(organization_id=membership.organization_id)
    return qs
