"""Наследование прав ролей (#39)."""
from __future__ import annotations

from delayu.models import Role, RoleModulePermission

PERM_FIELDS = (
    "can_view",
    "can_create",
    "can_change",
    "can_delete",
    "can_view_pii",
    "can_export_pii",
    "can_approve",
    "can_sign",
    "can_archive",
    "can_bulk",
)

ACTION_TO_FIELD = {
    "view": "can_view",
    "create": "can_create",
    "change": "can_change",
    "delete": "can_delete",
    "view_pii": "can_view_pii",
    "export_pii": "can_export_pii",
    "approve": "can_approve",
    "sign": "can_sign",
    "archive": "can_archive",
    "bulk": "can_bulk",
}


def role_chain(role: Role) -> list[Role]:
    """От предка к потомку (без циклов)."""
    chain: list[Role] = []
    seen: set[int] = set()
    cur: Role | None = role
    while cur and cur.pk not in seen:
        chain.insert(0, cur)
        seen.add(cur.pk)
        cur = cur.parent_role if getattr(cur, "parent_role_id", None) else None
    return chain


def effective_module_permission(role: Role, module) -> RoleModulePermission | None:
    """Объединённые флаги по цепочке наследования (OR)."""
    flags = {f: False for f in PERM_FIELDS}
    found = False
    for r in role_chain(role):
        perm = RoleModulePermission.objects.filter(role=r, module=module).first()
        if not perm:
            continue
        found = True
        for f in PERM_FIELDS:
            if getattr(perm, f, False):
                flags[f] = True
    if not found:
        return None
    stub = RoleModulePermission(role=role, module=module)
    for f, val in flags.items():
        setattr(stub, f, val)
    return stub


def role_has_action(role: Role, module, action: str) -> bool:
    field = ACTION_TO_FIELD.get(action)
    if not field:
        return False
    perm = effective_module_permission(role, module)
    return bool(perm and getattr(perm, field, False))


def effective_matrix_row(role: Role, module, own_perm: RoleModulePermission | None) -> dict:
    eff = effective_module_permission(role, module)
    inherited_only = False
    if eff and own_perm:
        inherited_only = any(
            getattr(eff, f, False) and not getattr(own_perm, f, False) for f in PERM_FIELDS
        )
    elif eff and not own_perm:
        inherited_only = True

    return {
        "code": module.code,
        "name": module.name,
        "view": bool(eff and eff.can_view),
        "create": bool(eff and eff.can_create),
        "change": bool(eff and eff.can_change),
        "delete": bool(eff and eff.can_delete),
        "view_pii": bool(eff and eff.can_view_pii),
        "export_pii": bool(eff and eff.can_export_pii),
        "approve": bool(eff and eff.can_approve),
        "sign": bool(eff and eff.can_sign),
        "archive": bool(eff and eff.can_archive),
        "bulk": bool(eff and eff.can_bulk),
        "inherited": inherited_only,
        "own": {
            "view": bool(own_perm and own_perm.can_view),
            "create": bool(own_perm and own_perm.can_create),
            "change": bool(own_perm and own_perm.can_change),
            "delete": bool(own_perm and own_perm.can_delete),
            "view_pii": bool(own_perm and own_perm.can_view_pii),
            "export_pii": bool(own_perm and own_perm.can_export_pii),
            "approve": bool(own_perm and own_perm.can_approve),
            "sign": bool(own_perm and own_perm.can_sign),
            "archive": bool(own_perm and own_perm.can_archive),
            "bulk": bool(own_perm and own_perm.can_bulk),
        },
    }
