"""Динамическое меню платформы по включённым модулям и правам."""

from __future__ import annotations

from delayu.models import Organization, Role, Subsystem, SubsystemMembership


MENU_SECTIONS = [
    {
        "header": "Главная",
        "items": [
            {"url_name": "platform-home", "codes": [], "icon": "ri-home-smile-line", "label": "Главная"},
        ],
    },
    {
        "header": "Ежедневная работа",
        "items": [
            {"url_name": "platform-cabinet", "codes": ["M07"], "icon": "ri-user-line", "label": "Личный кабинет"},
            {"url_name": "platform-today", "codes": ["M08"], "icon": "ri-calendar-check-line", "label": "Мне на сегодня"},
            {"url_name": "platform-calendar", "codes": ["M09"], "icon": "ri-calendar-line", "label": "Календарь"},
            {"url_name": "platform-kanban", "codes": ["M10"], "icon": "ri-kanban-view", "label": "Канбан"},
            {"url_name": "platform-gantt", "codes": ["M11"], "icon": "ri-bar-chart-horizontal-line", "label": "Гант"},
            {"url_name": "platform-favorites", "codes": ["M13"], "icon": "ri-star-line", "label": "Избранное"},
            {"url_name": "platform-cases", "codes": ["M22"], "icon": "ri-folder-line", "label": "Реестр дел"},
            {"url_name": "platform-inbox", "codes": ["M24"], "icon": "ri-mail-line", "label": "Корреспонденция"},
            {"url_name": "platform-notifications", "codes": ["M12"], "icon": "ri-notification-3-line", "label": "Уведомления"},
            {"url_name": "platform-activity", "codes": ["M14"], "icon": "ri-pulse-line", "label": "Лента активности"},
            {"url_name": "platform-help-center", "codes": [], "icon": "ri-question-line", "label": "Центр помощи"},
            {"url_name": "platform-onboarding-checklist", "codes": [], "icon": "ri-guide-line", "label": "Первые шаги"},
        ],
    },
    {
        "header": "Документы",
        "items": [
            {"url_name": "platform-documents", "codes": ["M05"], "icon": "ri-file-line", "label": "Документы"},
            {"url_name": "platform-inbox", "url_query": "?folder=sent", "codes": ["M25"], "icon": "ri-send-plane-line", "label": "Исходящие"},
            {"url_name": "platform-journal", "codes": ["M26"], "icon": "ri-book-2-line", "label": "Журнал регистрации"},
            {"url_name": "platform-print-templates", "codes": ["M29"], "icon": "ri-printer-line", "label": "Печатные формы"},
            {"url_name": "platform-signatures", "codes": ["M30"], "icon": "ri-quill-pen-line", "label": "Электронная подпись"},
            {"url_name": "platform-scan-batch", "codes": ["M32"], "icon": "ri-scanner-line", "label": "Сканирование"},
            {"url_name": "platform-goskey", "codes": ["M31"], "icon": "ri-government-line", "label": "Госключ"},
        ],
    },
    {
        "header": "Данные",
        "items": [
            {"url_name": "platform-registries", "codes": ["M23"], "icon": "ri-database-2-line", "label": "Реестры"},
            {"url_name": "platform-ai-search", "codes": ["M48"], "icon": "ri-search-line", "label": "Поиск"},
        ],
    },
    {
        "header": "НСИ и операции",
        "items": [
            {"url_name": "platform-ops", "codes": ["M73"], "icon": "ri-dashboard-line", "label": "Обзор"},
            {"url_name": "platform-nsi", "codes": ["M73"], "icon": "ri-list-check", "label": "НСИ"},
            {"url_name": "platform-form-schemas", "codes": ["M74"], "icon": "ri-layout-4-line", "label": "Конструктор форм"},
            {"url_name": "platform-bulk-ops", "codes": ["M75"], "icon": "ri-stack-line", "label": "Массовые операции"},
            {"url_name": "platform-exports", "codes": ["M76"], "icon": "ri-file-download-line", "label": "Выгрузки"},
            {"url_name": "platform-directives", "codes": ["M77"], "icon": "ri-task-line", "label": "Поручения"},
        ],
    },
    {
        "header": "Процессы",
        "items": [
            {"url_name": "platform-bpm-approvals", "codes": ["M34"], "icon": "ri-checkbox-circle-line", "label": "Согласования"},
            {"url_name": "platform-bpm", "codes": ["M33"], "icon": "ri-git-branch-line", "label": "Процессы"},
            {"url_name": "platform-bpm-templates", "codes": ["M33"], "icon": "ri-flow-chart", "label": "Конструктор BPM"},
            {"url_name": "platform-bpm-sla-monitor", "codes": ["M35"], "icon": "ri-timer-flash-line", "label": "SLA"},
            {"url_name": "platform-bpm-regulations", "codes": ["M36"], "icon": "ri-calendar-schedule-line", "label": "Регламенты сроков"},
        ],
    },
    {
        "header": "Коммуникации",
        "items": [
            {"url_name": "platform-chat", "codes": ["M37"], "icon": "ri-wechat-line", "label": "Чат"},
            {"url_name": "platform-comments", "codes": ["M38"], "icon": "ri-chat-3-line", "label": "Комментарии"},
            {"url_name": "platform-mentions", "codes": ["M39"], "icon": "ri-at-line", "label": "Упоминания"},
            {"url_name": "platform-subscriptions", "codes": ["M39"], "icon": "ri-notification-badge-line", "label": "Подписки"},
            {"url_name": "platform-meetings", "codes": ["M40"], "icon": "ri-vidicon-line", "label": "ВКС"},
            {"url_name": "platform-messengers", "codes": ["M41"], "icon": "ri-telegram-line", "label": "Мессенджеры"},
        ],
    },
    {
        "header": "Аналитика",
        "items": [
            {"url_name": "platform-dashboard", "codes": ["M15"], "icon": "ri-bar-chart-line", "label": "Дашборды"},
            {"url_name": "platform-reports", "codes": ["M16"], "icon": "ri-file-chart-line", "label": "Отчёты"},
            {"url_name": "platform-charts", "codes": ["M18"], "icon": "ri-line-chart-line", "label": "Графики"},
            {"url_name": "platform-regulatory", "codes": ["M17"], "icon": "ri-government-line", "label": "Регл. отчётность"},
            {"url_name": "platform-quality", "codes": ["M19"], "icon": "ri-award-line", "label": "Качество"},
            {"url_name": "platform-overdue", "codes": ["M20"], "icon": "ri-alarm-warning-line", "label": "Просрочки"},
            {"url_name": "platform-departments", "codes": ["M21"], "icon": "ri-building-4-line", "label": "По отделам"},
        ],
    },
    {
        "header": "ИИ",
        "items": [
            {"url_name": "platform-ai-hub", "codes": ["M47"], "icon": "ri-robot-line", "label": "ИИ-обзор"},
            {"url_name": "platform-ai-assistant", "codes": ["M47"], "icon": "ri-chat-smile-2-line", "label": "Ассистент"},
            {"url_name": "platform-ai-search", "codes": ["M48"], "icon": "ri-search-eye-line", "label": "Семантический поиск"},
            {"url_name": "platform-ai-tools", "codes": ["M47"], "icon": "ri-magic-line", "label": "Инструменты ИИ"},
            {"url_name": "platform-knowledge", "codes": ["M61"], "icon": "ri-book-open-line", "label": "База знаний"},
            {"url_name": "platform-ai-policies", "codes": ["M66"], "icon": "ri-shield-check-line", "label": "Политики ИИ"},
        ],
    },
    {
        "header": "Инфраструктура",
        "items": [
            {"url_name": "platform-infra", "codes": ["M67"], "icon": "ri-road-map-line", "label": "Обзор"},
            {"url_name": "platform-gis", "codes": ["M67"], "icon": "ri-map-2-line", "label": "Геопортал"},
            {"url_name": "platform-pwa", "codes": ["M68"], "icon": "ri-smartphone-line", "label": "PWA"},
            {"url_name": "platform-sso", "codes": ["M69"], "icon": "ri-shield-keyhole-line", "label": "SSO / ЕСИА"},
            {"url_name": "platform-etl", "codes": ["M70"], "icon": "ri-upload-cloud-2-line", "label": "ETL"},
            {"url_name": "platform-data-hub", "codes": ["M71"], "icon": "ri-database-2-line", "label": "Data Hub"},
            {"url_name": "platform-citizen", "codes": ["M72"], "icon": "ri-user-community-line", "label": "Портал гражданина"},
        ],
    },
    {
        "header": "АИС УЖВ",
        "template": "uzhv",
        "items": [
            {"url_name": "uzhv-hub", "codes": ["M22"], "icon": "ri-home-smile-line", "label": "Обзор УЖВ"},
            {"url_name": "uzhv-create-hub", "codes": ["M22"], "icon": "ri-magic-line", "label": "Мастер создания"},
            {"url_name": "uzhv-deadlines", "codes": ["M22"], "icon": "ri-calendar-event-line", "label": "Сроки"},
            {"url_name": "uzhv-cases", "codes": ["M22"], "icon": "ri-file-list-2-line", "label": "Учёт нуждающихся"},
            {"url_name": "uzhv-young-families", "codes": ["M22"], "icon": "ri-heart-2-line", "label": "Молодые семьи"},
            {"url_name": "uzhv-orphans", "codes": ["M22"], "icon": "ri-user-star-line", "label": "Дети-сироты"},
            {"url_name": "uzhv-interagency", "codes": ["M22"], "icon": "ri-exchange-box-line", "label": "Межвед. запросы"},
            {"url_name": "uzhv-citizens", "codes": ["M22"], "icon": "ri-user-heart-line", "label": "Граждане"},
            {"url_name": "uzhv-fund", "codes": ["M22"], "icon": "ri-building-4-line", "label": "Жилфонд"},
            {"url_name": "uzhv-personal-accounts", "codes": ["M22"], "icon": "ri-bank-card-line", "label": "Лицевые счета"},
            {"url_name": "uzhv-private-premises", "codes": ["M22"], "icon": "ri-home-3-line", "label": "Частный фонд"},
            {"url_name": "uzhv-inspections", "codes": ["M22"], "icon": "ri-shield-check-line", "label": "Жилконтроль"},
            {"url_name": "uzhv-inspection-plans", "codes": ["M22"], "icon": "ri-calendar-check-line", "label": "Планы проверок"},
            {"url_name": "uzhv-inspection-orders", "codes": ["M22"], "icon": "ri-file-list-line", "label": "Предписания на проверку"},
            {"url_name": "uzhv-enforcement", "codes": ["M22"], "icon": "ri-scales-2-line", "label": "Исп. производства"},
            {"url_name": "uzhv-prescriptions", "codes": ["M22"], "icon": "ri-file-warning-line", "label": "Предписания"},
            {"url_name": "uzhv-admin-protocols", "codes": ["M22"], "icon": "ri-file-shield-2-line", "label": "Протоколы об АП"},
            {"url_name": "uzhv-court-cases", "codes": ["M22"], "icon": "ri-scales-3-line", "label": "Судебные дела"},
            {"url_name": "uzhv-resettlement", "codes": ["M22"], "icon": "ri-home-gear-line", "label": "Расселение"},
            {"url_name": "uzhv-reconstruction", "codes": ["M22"], "icon": "ri-building-line", "label": "Реконструкция"},
            {"url_name": "uzhv-unfit-premises", "codes": ["M22"], "icon": "ri-home-smile-line", "label": "Непригодные"},
            {"url_name": "uzhv-contracts", "codes": ["M22"], "icon": "ri-file-paper-2-line", "label": "Договоры"},
            {"url_name": "uzhv-appeals", "codes": ["M24"], "icon": "ri-customer-service-2-line", "label": "Обращения"},
            {"url_name": "uzhv-reports", "codes": ["M15"], "icon": "ri-file-chart-line", "label": "Отчёты"},
        ],
    },
    {
        "header": "Администрирование",
        "items": [
            {"url_name": "platform-studio", "codes": ["M01"], "icon": "ri-palette-2-line", "label": "Студия ДелаЮ"},
            {"url_name": "platform-subsystems", "codes": ["M01"], "icon": "ri-settings-3-line", "label": "Подсистемы"},
            {"url_name": "platform-modules", "codes": ["M01"], "icon": "ri-apps-line", "label": "Каталог модулей"},
            {"url_name": "platform-users", "codes": ["M03"], "icon": "ri-group-line", "label": "Пользователи"},
            {"url_name": "platform-roles", "codes": ["M02"], "icon": "ri-shield-user-line", "label": "Роли и права"},
            {"url_name": "platform-structure", "codes": ["M04"], "icon": "ri-organization-chart", "label": "Структура (ШР)"},
            {"url_name": "platform-integrations", "codes": ["M42"], "icon": "ri-plug-line", "label": "Шлюз интеграций"},
            {"url_name": "platform-api-docs", "codes": ["M43"], "icon": "ri-code-s-slash-line", "label": "REST API"},
            {"url_name": "platform-smev", "codes": ["M44"], "icon": "ri-government-line", "label": "СМЭВ"},
            {"url_name": "platform-external", "codes": ["M45"], "icon": "ri-exchange-line", "label": "Внешние ИС"},
            {"url_name": "platform-archive-cases", "codes": ["M06"], "icon": "ri-archive-line", "label": "Архив дел"},
            {"url_name": "platform-audio", "codes": ["M46"], "icon": "ri-mic-line", "label": "Аудиоархив"},
            {"url_name": "platform-audit", "codes": ["M01"], "icon": "ri-file-list-3-line", "label": "Журнал аудита"},
        ],
    },
    {
        "header": "Эксплуатация",
        "items": [
            {"url_name": "platform-exploit", "codes": ["M78"], "icon": "ri-settings-4-line", "label": "Обзор"},
            {"url_name": "platform-notification-templates", "codes": ["M78"], "icon": "ri-mail-settings-line", "label": "Шаблоны уведомлений"},
            {"url_name": "platform-antivirus", "codes": ["M79"], "icon": "ri-shield-virus-line", "label": "Антивирус"},
            {"url_name": "platform-pii", "codes": ["M80"], "icon": "ri-eye-off-line", "label": "Маскирование ПДн"},
            {"url_name": "platform-backups", "codes": ["M81"], "icon": "ri-database-2-line", "label": "Бэкапы"},
            {"url_name": "platform-health", "codes": ["M82"], "icon": "ri-heart-pulse-line", "label": "Мониторинг"},
        ],
    },
    {
        "header": "UX и лицензии",
        "items": [
            {"url_name": "platform-ux", "codes": ["M83"], "icon": "ri-palette-line", "label": "Обзор UX"},
            {"url_name": "platform-licenses", "codes": ["M83"], "icon": "ri-key-line", "label": "Лицензии"},
            {"url_name": "platform-onboarding", "codes": ["M84"], "icon": "ri-graduation-cap-line", "label": "Обучение"},
            {"url_name": "platform-dashboard-layouts", "codes": ["M85"], "icon": "ri-layout-grid-line", "label": "Дашборды"},
            {"url_name": "platform-marketplace", "codes": ["M86"], "icon": "ri-store-2-line", "label": "Коннекторы"},
        ],
    },
]


def _enabled_codes(membership: SubsystemMembership) -> set[str]:
    return set(
        membership.subsystem.module_links.filter(enabled=True).values_list(
            "module__code", flat=True
        )
    )


def _role_view_codes(membership: SubsystemMembership) -> set[str]:
    return set(
        membership.role.module_permissions.filter(can_view=True).values_list(
            "module__code", flat=True
        )
    )


def build_menu_for_membership(membership: SubsystemMembership) -> list[dict]:
    from delayu.services import studio
    from delayu.services.scope import menu_item_allowed

    layout = membership.subsystem.menu_layout
    if layout:
        custom = studio.menu_layout_to_menu_json(layout, membership)
        if custom:
            from delayu.services.menu_badges import apply_menu_badges
            from delayu.services.scope import filter_menu_for_user

            filtered = filter_menu_for_user(custom, membership.user)
            return apply_menu_badges(filtered, membership.user, membership.subsystem)
    enabled = _enabled_codes(membership)
    allowed = _role_view_codes(membership)
    is_admin = membership.user.is_superuser
    template = membership.subsystem.industry_template
    menu: list[dict] = []
    for section in MENU_SECTIONS:
        if section.get("template") and section["template"] != template:
            continue
        section_items = []
        for item in section["items"]:
            if not menu_item_allowed(membership.user, item["url_name"]):
                continue
            codes = item.get("codes") or []
            if codes and not any(
                c in enabled and (c in allowed or is_admin) for c in codes
            ):
                continue
            from django.urls import reverse

            href = reverse(item["url_name"])
            if item.get("url_query"):
                href += item["url_query"]
            section_items.append(
                {
                    "url": item["url_name"],
                    "url_href": href,
                    "icon": f"menu-icon icon-base ri {item['icon']}",
                    "name": item["label"],
                    "slug": item["url_name"],
                }
            )
        if section_items:
            header_class = _section_header_class(section)
            item_class = _section_item_class(header_class)
            for entry in section_items:
                entry["menu_li_class"] = item_class
            menu.append({"menu_header": section["header"], "menu_header_class": header_class})
            menu.extend(section_items)
    return menu


def _section_header_class(section: dict) -> str:
    if section.get("template"):
        return "menu-header--subsystem"
    return ""


def _section_item_class(header_class: str) -> str:
    if header_class == "menu-header--subsystem":
        return "menu-item--subsystem"
    return ""


def _lookup_membership(user, subsystem_id=None) -> SubsystemMembership | None:
    qs = SubsystemMembership.objects.filter(user=user).select_related(
        "subsystem", "organization", "role"
    )
    if subsystem_id:
        return qs.filter(subsystem_id=subsystem_id).first()
    return qs.filter(is_default=True).first() or qs.first()


def _org_for_subsystem(sub: Subsystem) -> Organization:
    org = Organization.objects.filter(subsystem=sub, is_active=True).order_by("pk").first()
    if org:
        return org
    return Organization.objects.create(
        subsystem=sub,
        code="main",
        name=sub.name[:255] or sub.code,
    )


def ensure_superuser_membership(user) -> SubsystemMembership | None:
    """Superuser без membership → admin в УЖВ (или первой подсистеме)."""
    if not user.is_authenticated or not user.is_superuser:
        return None

    existing = _lookup_membership(user)
    if existing:
        return existing

    sub = (
        Subsystem.objects.filter(code="uzhv").exclude(status=Subsystem.Status.ARCHIVED).first()
        or Subsystem.objects.exclude(status=Subsystem.Status.ARCHIVED).order_by("pk").first()
    )
    if not sub:
        return None

    role = (
        Role.objects.filter(subsystem=sub, code="uzhv_admin").first()
        or Role.objects.filter(subsystem=sub, code="admin").first()
        or Role.objects.filter(subsystem=sub).order_by("pk").first()
    )
    if not role:
        return None

    org = _org_for_subsystem(sub)
    membership, _created = SubsystemMembership.objects.update_or_create(
        user=user,
        subsystem=sub,
        organization=org,
        role=role,
        defaults={"is_default": True},
    )
    SubsystemMembership.objects.filter(user=user).exclude(pk=membership.pk).update(
        is_default=False
    )
    if not membership.is_default:
        membership.is_default = True
        membership.save(update_fields=["is_default"])
    return membership


def get_active_membership(user, subsystem_id=None) -> SubsystemMembership | None:
    membership = _lookup_membership(user, subsystem_id=subsystem_id)
    if membership or subsystem_id or not getattr(user, "is_authenticated", False):
        return membership
    if user.is_superuser:
        return ensure_superuser_membership(user)
    return None
