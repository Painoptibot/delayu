"""M02 — роли и матрица прав."""
from django.db import transaction

from delayu.models import ModuleCatalog, Role, RoleModulePermission, SubsystemMembership, SubsystemModule

PERM_ACTIONS = ("view", "create", "change", "delete")


def enabled_modules_for_subsystem(subsystem):
    codes = SubsystemModule.objects.filter(subsystem=subsystem, enabled=True).values_list(
        "module_id", flat=True
    )
    return ModuleCatalog.objects.filter(id__in=codes, is_active=True).order_by("sort_order", "code")


def permissions_from_post(post_data, subsystem):
    """Разбор полей perm_<CODE>_<action> из POST."""
    modules = {m.code: m for m in enabled_modules_for_subsystem(subsystem)}
    result = {}
    for mod_code, module in modules.items():
        perms = {}
        for action in PERM_ACTIONS:
            key = f"perm_{mod_code}_{action}"
            perms[action] = bool(post_data.get(key))
        result[module] = perms
    return result


def permissions_to_form_initial(role, subsystem):
    initial = {}
    modules = enabled_modules_for_subsystem(subsystem)
    for mod in modules:
        perm = RoleModulePermission.objects.filter(role=role, module=mod).first()
        for action in PERM_ACTIONS:
            initial[f"perm_{mod.code}_{action}"] = bool(
                perm and getattr(perm, f"can_{action}", False)
            )
    return initial


@transaction.atomic
def save_role_permissions(role, subsystem, permissions_map):
    for module, perms in permissions_map.items():
        if not any(perms.values()):
            RoleModulePermission.objects.filter(role=role, module=module).delete()
            continue
        RoleModulePermission.objects.update_or_create(
            role=role,
            module=module,
            defaults={
                "can_view": perms.get("view", False),
                "can_create": perms.get("create", False),
                "can_change": perms.get("change", False),
                "can_delete": perms.get("delete", False),
            },
        )


def build_matrix_rows(form, subsystem):
    """Строки таблицы прав для шаблона (поля формы по модулям)."""
    rows = []
    for mod in enabled_modules_for_subsystem(subsystem):
        cells = []
        for action in PERM_ACTIONS:
            fname = f"perm_{mod.code}_{action}"
            cells.append({"action": action, "field": form[fname] if fname in form.fields else ""})
        rows.append({"mod": mod, "cells": cells})
    return rows


def role_card_context(role):
    memberships_count = SubsystemMembership.objects.filter(role=role).count()
    perms = (
        RoleModulePermission.objects.filter(role=role)
        .select_related("module")
        .order_by("module__sort_order", "module__code")
    )
    rows = []
    for p in perms:
        flags = []
        if p.can_view:
            flags.append("просмотр")
        if p.can_create:
            flags.append("создание")
        if p.can_change:
            flags.append("изменение")
        if p.can_delete:
            flags.append("удаление")
        rows.append(
            {
                "code": p.module.code,
                "name": p.module.name,
                "flags": ", ".join(flags) if flags else "—",
            }
        )
    return {
        "role": role,
        "memberships_count": memberships_count,
        "permission_rows": rows,
    }


@transaction.atomic
def copy_role(source_role, new_code, new_name):
    if Role.objects.filter(subsystem=source_role.subsystem, code=new_code).exists():
        raise ValueError("Роль с таким кодом уже существует")
    new_role = Role.objects.create(
        subsystem=source_role.subsystem,
        code=new_code,
        name=new_name,
        description=f"Копия: {source_role.description}",
        is_system=False,
    )
    for p in RoleModulePermission.objects.filter(role=source_role):
        RoleModulePermission.objects.create(
            role=new_role,
            module=p.module,
            can_view=p.can_view,
            can_create=p.can_create,
            can_change=p.can_change,
            can_delete=p.can_delete,
        )
    return new_role
