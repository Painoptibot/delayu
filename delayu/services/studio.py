"""Студия ДелаЮ — общие данные и утилиты визуальных конструкторов."""
from __future__ import annotations

from delayu.menu import MENU_SECTIONS

FORM_FIELD_TYPES = [
    {"type": "text", "label": "Текст", "icon": "ri-text"},
    {"type": "textarea", "label": "Многострочный", "icon": "ri-file-text-line"},
    {"type": "date", "label": "Дата", "icon": "ri-calendar-line"},
    {"type": "select", "label": "Список (НСИ)", "icon": "ri-list-check"},
    {"type": "number", "label": "Число", "icon": "ri-hashtag"},
    {"type": "file", "label": "Файл", "icon": "ri-attachment-line"},
]

BPM_NODE_TYPES = [
    {"type": "start", "label": "Старт", "color": "#71dd37"},
    {"type": "task", "label": "Задача", "color": "#696cff"},
    {"type": "approval", "label": "Согласование", "color": "#03c3ec"},
    {"type": "gateway", "label": "Развилка", "color": "#ffab00"},
    {"type": "timer", "label": "Таймер SLA", "color": "#ff3e1d"},
    {"type": "end", "label": "Финиш", "color": "#8592a3"},
]

DASHBOARD_WIDGETS = [
    {"id": "kpi_cases", "label": "Дела в работе", "w": 3, "h": 1},
    {"id": "kpi_tasks", "label": "Открытые задачи", "w": 3, "h": 1},
    {"id": "kpi_corr", "label": "Входящие", "w": 3, "h": 1},
    {"id": "kpi_bpm", "label": "Согласования", "w": 3, "h": 1},
    {"id": "chart_cases", "label": "График дел", "w": 6, "h": 2},
    {"id": "chart_tasks", "label": "Задачи по приоритету", "w": 6, "h": 2},
    {"id": "table_overdue", "label": "Просрочки", "w": 12, "h": 2},
    {"id": "feed_activity", "label": "Лента активности", "w": 6, "h": 2},
]

CABINET_WIDGETS = [
    {"id": "profile", "label": "Профиль", "icon": "ri-user-line"},
    {"id": "tasks_today", "label": "Задачи на сегодня", "icon": "ri-calendar-check-line"},
    {"id": "bpm_pending", "label": "Согласования", "icon": "ri-checkbox-circle-line"},
    {"id": "notifications", "label": "Уведомления", "icon": "ri-notification-3-line"},
    {"id": "favorites", "label": "Избранное", "icon": "ri-star-line"},
    {"id": "inbox_preview", "label": "Входящие", "icon": "ri-mail-line"},
]

TODAY_WIDGETS = [
    {"id": "kpi_today", "label": "На сегодня", "icon": "ri-calendar-check-line"},
    {"id": "kpi_overdue", "label": "Просрочено", "icon": "ri-alarm-warning-line"},
    {"id": "kpi_priority", "label": "Высокий приоритет", "icon": "ri-flag-line"},
    {"id": "kpi_no_due", "label": "Без срока", "icon": "ri-time-line"},
    {"id": "tasks_table", "label": "Таблица задач", "icon": "ri-list-check"},
    {"id": "quick_inbox", "label": "Входящие", "icon": "ri-inbox-line"},
]

CORR_WORKFLOW_STEPS = [
    {"id": "register", "label": "Регистрация", "icon": "ri-inbox-archive-line"},
    {"id": "assign", "label": "Назначение", "icon": "ri-user-add-line"},
    {"id": "execute", "label": "Исполнение", "icon": "ri-task-line"},
    {"id": "review", "label": "Проверка", "icon": "ri-eye-line"},
    {"id": "reply", "label": "Ответ / исходящее", "icon": "ri-send-plane-line"},
    {"id": "archive", "label": "Архив", "icon": "ri-archive-line"},
]

PRINT_VARIABLES = [
    "{{reg_number}}",
    "{{subject}}",
    "{{counterparty}}",
    "{{reg_date}}",
    "{{direction}}",
    "{{status}}",
    "{{case.number}}",
    "{{case.title}}",
]

INTEGRATION_PIPELINE_NODES = [
    {"type": "source", "label": "Источник", "icon": "ri-download-cloud-line"},
    {"type": "map", "label": "Маппинг полей", "icon": "ri-arrow-left-right-line"},
    {"type": "transform", "label": "Трансформация", "icon": "ri-code-line"},
    {"type": "validate", "label": "Валидация", "icon": "ri-shield-check-line"},
    {"type": "endpoint", "label": "Endpoint", "icon": "ri-plug-line"},
    {"type": "dry_run", "label": "Dry-run", "icon": "ri-play-circle-line"},
]

PERM_PRESETS = {
    "operator": {"view": True, "create": True, "change": True, "delete": False},
    "viewer": {"view": True, "create": False, "change": False, "delete": False},
    "admin": {"view": True, "create": True, "change": True, "delete": True},
}

STUDIO_DASHBOARD_IDS = {w["id"] for w in DASHBOARD_WIDGETS}

STUDIO_DASHBOARD_RUNTIME_MAP = {
    "kpi_cases": "kpi_cases",
    "kpi_tasks": "kpi_tasks",
    "kpi_corr": "kpi_corr",
    "kpi_bpm": "kpi_bpm",
    "chart_cases": "chart_sessions",
    "chart_tasks": "chart_priority",
    "table_overdue": "list_overdue",
    "feed_activity": "feed_activity",
}

KPI_ROW_CHILDREN = frozenset(
    {"kpi_cases", "kpi_overdue", "kpi_tasks", "kpi_bpm", "kpi_corr"}
)


def _widget_id(entry):
    if isinstance(entry, dict):
        return entry.get("id") or ""
    return str(entry)


def normalize_dashboard_widgets(raw: list) -> list:
    """Привести раскладку Студии/M85 к id виджетов страницы KPI-дашборда."""
    if not raw:
        return []
    if not any(_widget_id(w) in STUDIO_DASHBOARD_IDS for w in raw):
        return raw

    out = []
    seen = set()
    for entry in raw:
        wid = _widget_id(entry)
        rid = STUDIO_DASHBOARD_RUNTIME_MAP.get(wid, wid)
        if not rid or rid in seen:
            continue
        seen.add(rid)
        col = 12
        if isinstance(entry, dict) and entry.get("w"):
            col = min(12, max(3, int(entry["w"]) * 3))
        out.append({"id": rid, "col": col})

    if seen & KPI_ROW_CHILDREN:
        out.insert(0, {"id": "kpi_row", "col": 12})
    return out


def cabinet_widgets_for_profile(profile) -> list[str]:
    prefs = profile.theme_prefs or {}
    widgets = prefs.get("cabinet_widgets")
    if widgets:
        if isinstance(widgets[0], str):
            return list(widgets)
        return [_widget_id(w) for w in widgets if _widget_id(w)]
    return [w["id"] for w in CABINET_WIDGETS]


def today_widgets_for_profile(profile) -> list[str]:
    prefs = profile.theme_prefs or {}
    widgets = prefs.get("today_widgets")
    if widgets and isinstance(widgets, list):
        return [w for w in widgets if isinstance(w, str) and w]
    return [w["id"] for w in TODAY_WIDGETS]


def save_today_widgets(profile, widget_ids: list[str]) -> list[str]:
    allowed = {w["id"] for w in TODAY_WIDGETS}
    cleaned = [w for w in widget_ids if w in allowed]
    if not cleaned:
        cleaned = [w["id"] for w in TODAY_WIDGETS]
    prefs = dict(profile.theme_prefs or {})
    prefs["today_widgets"] = cleaned
    profile.theme_prefs = prefs
    profile.save(update_fields=["theme_prefs", "updated_at"])
    return cleaned


def flat_menu_items():
    """Все пункты меню для drag-constructor."""
    items = []
    for section in MENU_SECTIONS:
        for item in section["items"]:
            items.append(
                {
                    "url_name": item["url_name"],
                    "label": item["label"],
                    "icon": item["icon"],
                    "codes": item.get("codes") or [],
                    "section": section["header"],
                    "url_query": item.get("url_query", ""),
                }
            )
    return items


def default_menu_layout():
    layout = []
    for section in MENU_SECTIONS:
        layout.append(
            {
                "header": section["header"],
                "items": [i["url_name"] for i in section["items"]],
            }
        )
    return layout


def menu_layout_to_menu_json(layout, membership):
    """Собрать меню из сохранённой раскладки."""
    from django.urls import reverse

    from delayu.menu import _enabled_codes, _role_view_codes

    flat = {i["url_name"]: i for i in flat_menu_items()}
    enabled = _enabled_codes(membership)
    allowed = _role_view_codes(membership)
    is_admin = membership.user.is_superuser
    menu = []
    for block in layout or []:
        header = block.get("header", "")
        section_items = []
        for url_name in block.get("items") or []:
            item = flat.get(url_name)
            if not item:
                continue
            codes = item.get("codes") or []
            if codes and not any(c in enabled and (c in allowed or is_admin) for c in codes):
                continue
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
            menu.append({"menu_header": header})
            menu.extend(section_items)
    return menu


def diagram_to_bpm_steps(diagram: dict) -> list:
    """Конвертация диаграммы студии в steps JSON для движка BPM."""
    nodes = {n["id"]: n for n in diagram.get("nodes") or []}
    edges = diagram.get("edges") or []
    order = []
    seen = set()
    start = next((n for n in nodes.values() if n.get("type") == "start"), None)
    if not start:
        return []
    queue = [start["id"]]
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = nodes.get(nid)
        if not node or node.get("type") in ("start", "end"):
            pass
        elif node.get("type") in ("task", "approval"):
            order.append(
                {
                    "id": nid,
                    "name": node.get("label") or nid,
                    "assignee_id": node.get("assignee_id"),
                }
            )
        for e in edges:
            if e.get("from") == nid and e.get("to") not in seen:
                queue.append(e["to"])
    return order


def default_correspondence_workflow():
    return {
        "steps": [s["id"] for s in CORR_WORKFLOW_STEPS],
        "sla_days": {"register": 1, "assign": 2, "execute": 10, "review": 3},
    }
