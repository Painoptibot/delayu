"""Матрица ролей АИС УЖВ по ТЗ (п. 187–210)."""
from delayu.services.scope import UZHV_MODULE_CODES

UZHV_ADMIN_DENY = {"M42", "M43", "M44", "M45", "M67", "M68", "M69", "M70", "M71", "M72", "M83", "M86"}

# Коды, по которым собрано меню контура. Платформенные разделы (канбан, документы, BPM) сюда не входят.
CONTOUR_MENU_CODES = (
    "M22",
    "U01",
    "M24",
    "U02",
    "M15",
    "M16",
    "U03",
    "U04",
)

# Пустые коды меню: эти пункты видны всем, пока их явно не убрать.
PLATFORM_SHELL_URLS = frozenset(
    {"platform-home", "platform-help-center", "platform-onboarding-checklist"}
)

# Префиксы адресов одного отдела. Нет записи — роль видит весь контур УЖВ.
DEPARTMENT_PREFIXES: dict[str, tuple[str, ...]] = {
    "uzhv_queue_spec": (
        "uzhv-hub",
        "uzhv-create-hub",
        "uzhv-create-chain",
        "uzhv-deadlines",
        "uzhv-cases",
        "uzhv-case-",
        "uzhv-queue-",
        "uzhv-young-famil",
        "uzhv-citizen",
        "uzhv-interagency",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_specialist": (
        "uzhv-hub",
        "uzhv-create-hub",
        "uzhv-create-chain",
        "uzhv-deadlines",
        "uzhv-cases",
        "uzhv-case-",
        "uzhv-queue-",
        "uzhv-young-famil",
        "uzhv-citizen",
        "uzhv-interagency",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_orphan_spec": (
        "uzhv-orphan",
        "uzhv-citizen",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_contract_spec": (
        "uzhv-contract",
        "uzhv-personal-account",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_fund_spec": (
        "uzhv-fund",
        "uzhv-building",
        "uzhv-premise",
        "uzhv-personal-account",
        "uzhv-private-premise",
        "uzhv-resettlement",
        "uzhv-reconstruction",
        "uzhv-unfit",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_inspector": (
        "uzhv-inspection",
        "uzhv-prescription",
        "uzhv-admin-protocol",
        "uzhv-court-case",
        "uzhv-enforcement",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_appeals_spec": (
        "uzhv-appeal",
        "uzhv-deadlines",
        "uzhv-support",
        "uzhv-qr",
        "uzhv-bulk",
    ),
    "uzhv_report_spec": (
        "uzhv-report",
        "uzhv-support",
    ),
}

# (can_view, can_create, can_change, can_delete) — None = как can_view для create/change
ROLE_SPECS: dict[str, dict] = {
    "uzhv_admin": {"label": "Администратор", "system": True, "all_modules": True, "deny": UZHV_ADMIN_DENY},
    "uzhv_head": {
        "label": "Начальник УЖВ",
        "system": True,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M15", "M16", "M22", "M24", "M28", "U01", "U02", "U03"),
        "change": ("M15", "M16", "M22", "M24", "M28", "M73", "U01", "U02", "U03"),
        "delete": (),
    },
    "uzhv_deputy": {
        "label": "Заместитель начальника",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": True,
        "change": True,
        "delete": ("M02", "M03"),
    },
    "uzhv_queue_spec": {
        "label": "Специалист по учёту",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "M73", "M74", "U01"),
        "change": ("M22", "M73", "M74", "U01"),
        "delete": (),
    },
    "uzhv_orphan_spec": {
        "label": "Специалист (дети-сироты)",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "U01"),
        "change": ("M22", "U01"),
        "delete": (),
    },
    "uzhv_contract_spec": {
        "label": "Специалист по договорам",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "U01"),
        "change": ("M22", "U01"),
        "delete": (),
    },
    "uzhv_fund_spec": {
        "label": "Специалист по жилфонду",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "U01"),
        "change": ("M22", "U01"),
        "delete": (),
    },
    "uzhv_inspector": {
        "label": "Инспектор (жилконтроль)",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "M24", "U01", "U02"),
        "change": ("M22", "M24", "U01", "U02"),
        "delete": (),
    },
    "uzhv_appeals_spec": {
        "label": "Специалист по обращениям",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M24", "M25", "U02"),
        "change": ("M24", "M25", "U02"),
        "delete": (),
    },
    "uzhv_report_spec": {
        "label": "Специалист отчётности",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M15", "M16", "U03"),
        "change": ("M15", "M16", "U03"),
        "delete": (),
    },
    "uzhv_viewer": {
        "label": "Наблюдатель",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": (),
        "change": (),
        "delete": (),
    },
    # обратная совместимость с демо-учётками
    "uzhv_manager": {
        "label": "Руководитель УЖВ",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": True,
        "change": True,
        "delete": ("M02", "M03"),
    },
    "uzhv_specialist": {
        "label": "Специалист УЖВ",
        "system": False,
        "modules": CONTOUR_MENU_CODES,
        "create": ("M22", "M24", "M73", "M74", "U01", "U02"),
        "change": ("M22", "M24", "M73", "M74", "U01", "U02"),
        "delete": (),
    },
}


SUPPORT_STAFF_ROLES = frozenset(
    {"uzhv_admin", "uzhv_head", "uzhv_deputy", "uzhv_manager"}
)


def department_prefixes(role_code: str) -> tuple[str, ...] | None:
    """None — роль видит все разделы контура. Кортеж — только свой отдел."""
    return DEPARTMENT_PREFIXES.get(role_code)


DEPARTMENT_HOME = {
    "uzhv_queue_spec": "uzhv-cases",
    "uzhv_specialist": "uzhv-cases",
    "uzhv_orphan_spec": "uzhv-orphans",
    "uzhv_contract_spec": "uzhv-contracts",
    "uzhv_fund_spec": "uzhv-fund",
    "uzhv_inspector": "uzhv-inspections",
    "uzhv_appeals_spec": "uzhv-appeals",
    "uzhv_report_spec": "uzhv-reports",
}


def department_home(role_code: str) -> str | None:
    return DEPARTMENT_HOME.get(role_code)


def url_in_department(role_code: str, url_name: str) -> bool:
    prefixes = department_prefixes(role_code)
    if not prefixes:
        return True
    name = url_name or ""
    return any(name == prefix or name.startswith(prefix) for prefix in prefixes)


def perm_for_role(role_code: str, mod_code: str) -> dict:
    spec = ROLE_SPECS.get(role_code, ROLE_SPECS["uzhv_viewer"])
    deny = spec.get("deny") or set()
    if mod_code in deny:
        return {"can_view": False, "can_create": False, "can_change": False, "can_delete": False}
    if mod_code == "U04":
        if spec.get("all_modules") or mod_code in (spec.get("modules") or ()):
            staff = role_code in SUPPORT_STAFF_ROLES or bool(spec.get("all_modules"))
            return {
                "can_view": True,
                "can_create": True,
                "can_change": staff,
                "can_delete": False,
            }
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
    if mod_code not in modules:
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
