"""Разделение контуров: платформа ЮГИт (глобально) vs подсистема (УЖВ и др.)."""
from __future__ import annotations

# Пункты меню только для администратора платформы (superuser / контур ЮГИт)
PLATFORM_ONLY_URL_NAMES = frozenset(
    {
        "platform-studio",
        "platform-subsystems",
        "platform-modules",
        "platform-integrations",
        "platform-api-docs",
        "platform-smev",
        "platform-external",
        "platform-infra",
        "platform-gis",
        "platform-pwa",
        "platform-sso",
        "platform-etl",
        "platform-data-hub",
        "platform-citizen",
        "platform-mail-settings",
        "platform-licenses",
        "platform-marketplace",
        "platform-ux",
    }
)

# Префиксы URL — только платформа
PLATFORM_ONLY_PATH_PREFIXES = (
    "/administration/subsystems/",
    "/administration/modules/",
    "/integrations/",
    "/infra/",
    "/exploit/mail/",
    "/ux/licenses/",
    "/ux/marketplace/",
    "/studio/",
)

# Модули, включаемые в подсистему «АИС УЖВ» (этап 1, без I-xx)
UZHV_MODULE_CODES = (
    "M02",
    "M03",
    "M04",
    "M05",
    "M06",
    "M07",
    "M08",
    "M09",
    "M10",
    "M11",
    "M12",
    "M13",
    "M14",
    "M15",
    "M16",
    "M22",
    "M23",
    "M24",
    "M25",
    "M26",
    "M27",
    "M28",
    "M29",
    "M33",
    "M34",
    "M35",  # SLA
    "M36",  # регламенты сроков
    "M18",  # графики
    "M19",  # качество
    "M20",  # мониторинг просрочек
    "M77",  # поручения
    "M73",
    "M74",
    "M75",
    "M76",
    "M78",
    "M80",
    "M85",
    "M01",  # аудит подсистемы (без каталога подсистем — фильтр меню)
    "U01",
    "U02",
    "U03",
    "U04",
)


def is_platform_admin(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    profile = getattr(user, "delayu_profile", None)
    if profile is None:
        from delayu.models import UserProfile

        profile = UserProfile.objects.filter(user=user).first()
    return bool(profile and profile.is_platform_admin)


def is_subsystem_scoped_user(user) -> bool:
    """Пользователь работает в контуре подсистемы, не на уровне платформы."""
    return user.is_authenticated and not user.is_superuser


def menu_item_allowed(user, url_name: str) -> bool:
    if url_name not in PLATFORM_ONLY_URL_NAMES:
        return True
    return is_platform_admin(user)


def path_requires_platform_admin(path: str) -> bool:
    return any(path.startswith(p) for p in PLATFORM_ONLY_PATH_PREFIXES)


def _uzhv_menu_entry_visible(user, url_name: str) -> bool:
    """Администратор контура видит платформу. Остальные роли УЖВ — только свой отдел или весь контур."""
    if not url_name or not getattr(user, "is_authenticated", False):
        return True
    from delayu.menu import _lookup_membership
    from delayu.services.uzhv_roles import PLATFORM_SHELL_URLS, url_in_department

    membership = _lookup_membership(user)
    if not membership or membership.subsystem.industry_template != "uzhv":
        return True
    role_code = getattr(membership.role, "code", "") or ""
    if role_code != "uzhv_admin" and (
        url_name in PLATFORM_SHELL_URLS or url_name.startswith("platform-")
    ):
        return False
    return url_in_department(role_code, url_name)


def filter_menu_for_user(menu: list, user) -> list:
    if is_platform_admin(user):
        return menu
    out = []
    for entry in menu:
        if "menu_header" in entry:
            out.append(entry)
            continue
        url_name = entry.get("url", "")
        if menu_item_allowed(user, url_name) and _uzhv_menu_entry_visible(user, url_name):
            out.append(entry)
    # убрать пустые секции
    cleaned = []
    i = 0
    while i < len(out):
        if "menu_header" in out[i]:
            header = out[i]
            items = []
            j = i + 1
            while j < len(out) and "menu_header" not in out[j]:
                items.append(out[j])
                j += 1
            if items:
                cleaned.append(header)
                cleaned.extend(items)
            i = j
        else:
            cleaned.append(out[i])
            i += 1
    return cleaned
