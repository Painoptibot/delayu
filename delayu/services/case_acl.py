"""Case-level ACL (#19)."""
from delayu.menu import get_active_membership


def user_can_view_case(user, case) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    m = get_active_membership(user)
    if not m or case.subsystem_id != m.subsystem_id:
        return False
    if case.assignee_id == user.pk or case.created_by_id == user.pk:
        return True
    from delayu.services.delegation import delegation_principals

    principals = delegation_principals(user, m.subsystem)
    if case.assignee_id in principals or case.created_by_id in principals:
        return True
    role_code = (m.role.code or "").lower()
    if role_code in ("admin", "director", "auditor"):
        return True
    if case.organization_id and m.organization_id == case.organization_id:
        return True
    return False
