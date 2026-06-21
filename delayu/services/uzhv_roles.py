"""Матрица ролей АИС УЖВ по ТЗ (п. 187–210)."""
from delayu.services.scope import UZHV_MODULE_CODES

UZHV_ADMIN_DENY = {"M42", "M43", "M44", "M45", "M67", "M68", "M69", "M70", "M71", "M72", "M83", "M86"}

# (can_view, can_create, can_change, can_delete) — None = как can_view для create/change
ROLE_SPECS: dict[str, dict] = {
    "uzhv_admin": {"label": "Администратор", "system": True, "all_modules": True, "deny": UZHV_ADMIN_DENY},
    "uzhv_head": {
        "label": "Начальник УЖВ",
        "system": True,
        "modules": UZHV_MODULE_CODES,
        "create": ("M15", "M16", "M22", "M24", "M28"),
        "change": ("M15", "M16", "M22", "M24", "M28", "M73"),
        "delete": (),
    },
    "uzhv_deputy": {
        "label": "Заместитель начальника",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": True,
        "change": True,
        "delete": ("M02", "M03"),
    },
    "uzhv_queue_spec": {
        "label": "Специалист по учёту",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22", "M73", "M74"),
        "change": ("M22", "M73", "M74"),
        "delete": (),
    },
    "uzhv_orphan_spec": {
        "label": "Специалист (дети-сироты)",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22",),
        "change": ("M22",),
        "delete": (),
    },
    "uzhv_contract_spec": {
        "label": "Специалист по договорам",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22",),
        "change": ("M22",),
        "delete": (),
    },
    "uzhv_fund_spec": {
        "label": "Специалист по жилфонду",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22",),
        "change": ("M22",),
        "delete": (),
    },
    "uzhv_inspector": {
        "label": "Инспектор (жилконтроль)",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22", "M24"),
        "change": ("M22", "M24"),
        "delete": (),
    },
    "uzhv_appeals_spec": {
        "label": "Специалист по обращениям",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M24", "M25"),
        "change": ("M24", "M25"),
        "delete": (),
    },
    "uzhv_report_spec": {
        "label": "Специалист отчётности",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M15", "M16"),
        "change": ("M15", "M16"),
        "delete": (),
    },
    "uzhv_viewer": {
        "label": "Наблюдатель",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": (),
        "change": (),
        "delete": (),
    },
    # обратная совместимость с демо-учётками
    "uzhv_manager": {
        "label": "Руководитель УЖВ",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": True,
        "change": True,
        "delete": ("M02", "M03"),
    },
    "uzhv_specialist": {
        "label": "Специалист УЖВ",
        "system": False,
        "modules": UZHV_MODULE_CODES,
        "create": ("M22", "M24", "M73", "M74"),
        "change": ("M22", "M24", "M73", "M74"),
        "delete": (),
    },
}


def perm_for_role(role_code: str, mod_code: str) -> dict:
    spec = ROLE_SPECS.get(role_code, ROLE_SPECS["uzhv_viewer"])
    deny = spec.get("deny") or set()
    if mod_code in deny:
        return {"can_view": False, "can_create": False, "can_change": False, "can_delete": False}

    if spec.get("all_modules"):
        in_set = mod_code in UZHV_MODULE_CODES or mod_code == "M01"
        if not in_set:
            return {
                "can_view": False,
                "can_create": False,
                "can_change": False,
                "can_delete": False,
            }
        # Администратор УЖВ: полный доступ к операционным модулям (кроме deny выше)
        return {
            "can_view": True,
            "can_create": True,
            "can_change": True,
            "can_delete": mod_code in ("M02", "M03", "M73", "M74"),
        }

    modules = spec.get("modules") or ()
    if mod_code not in modules and mod_code != "M01":
        return {"can_view": False, "can_create": False, "can_change": False, "can_delete": False}

    create_spec = spec.get("create")
    change_spec = spec.get("change")
    delete_spec = spec.get("delete") or ()

    def _allow(flag, code):
        if flag is True:
            return True
        if flag is False or flag == ():
            return False
        return code in flag

    return {
        "can_view": True,
        "can_create": _allow(create_spec, mod_code),
        "can_change": _allow(change_spec, mod_code),
        "can_delete": mod_code in delete_spec if isinstance(delete_spec, (tuple, list, set)) else False,
    }
