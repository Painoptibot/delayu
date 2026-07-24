"""Матрица ролей инвестконтура Кубани."""

INVEST_MODULE_CODES = (
    "M02",
    "M03",
    "M15",
    "M22",
)

ROLE_SPECS: dict[str, dict] = {
    "invest_admin": {
        "label": "Администратор",
        "system": True,
        "all_modules": True,
    },
    "invest_agency": {
        "label": "Агентство",
        "system": False,
        "modules": INVEST_MODULE_CODES,
        "create": True,
        "change": True,
        "delete": (),
    },
    "invest_dept": {
        "label": "Департамент",
        "system": False,
        "modules": INVEST_MODULE_CODES,
        "create": True,
        "change": True,
        "delete": (),
    },
    "invest_mo": {
        "label": "МО",
        "system": False,
        "modules": INVEST_MODULE_CODES,
        "create": True,
        "change": True,
        "delete": (),
    },
    "invest_viewer": {
        "label": "Наблюдатель",
        "system": False,
        "modules": INVEST_MODULE_CODES,
        "create": (),
        "change": (),
        "delete": (),
    },
}


def perm_for_role(role_code: str, mod_code: str) -> dict:
    spec = ROLE_SPECS.get(role_code)
    if spec is None:
        return {
            "can_view": False,
            "can_create": False,
            "can_change": False,
            "can_delete": False,
        }
    modules = INVEST_MODULE_CODES + ("M01",)

    if spec.get("all_modules"):
        if mod_code not in modules:
            return {
                "can_view": False,
                "can_create": False,
                "can_change": False,
                "can_delete": False,
            }
        return {
            "can_view": True,
            "can_create": True,
            "can_change": True,
            "can_delete": True,
        }

    allowed = spec.get("modules") or ()
    if mod_code not in allowed and mod_code != "M01":
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
