# delayu/services/invest_automation_access.py
"""Who may manage invest automation UI (connection/flags/mapping/status)."""
from __future__ import annotations

from delayu.services.scope import is_platform_admin


def user_can_manage_invest_automation(user, membership) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or is_platform_admin(user):
        return True
    role = getattr(membership, "role", None)
    return bool(role and role.code == "invest_admin")
