"""Сравнение снимков конфигурации Студии (#6 / diff ревизий)."""
from __future__ import annotations


def _menu_item_count(layout) -> int:
    total = 0
    for sec in layout or []:
        if isinstance(sec, dict):
            total += len(sec.get("items") or [])
    return total


def _list_len(value) -> int:
    return len(value) if isinstance(value, list) else 0


def _summarize_change(key: str, before, after) -> dict:
    labels = {
        "menu_layout": "Меню",
        "correspondence_workflow": "Маршрут СЭД",
        "forms": "Формы",
        "bpm": "BPM-шаблоны",
        "print": "Печатные формы",
        "nsi": "НСИ",
        "integrations": "Интеграции",
        "role_layouts": "Ролевые раскладки",
        "policies": "Политики",
    }
    label = labels.get(key, key)
    if key == "menu_layout":
        b = _menu_item_count(before)
        a = _menu_item_count(after)
        detail = f"Пунктов меню: {b} → {a}"
    elif key == "correspondence_workflow":
        b_steps = len((before or {}).get("steps") or [])
        a_steps = len((after or {}).get("steps") or [])
        detail = f"Этапов СЭД: {b_steps} → {a_steps}"
    elif key == "policies":
        b = before or {}
        a = after or {}
        detail = (
            f"Хранение {b.get('retention_years', '—')}→{a.get('retention_years', '—')} лет, "
            f"SIEM {'вкл' if a.get('siem_enabled') else 'выкл'}"
        )
    elif isinstance(before, list) or isinstance(after, list):
        b = _list_len(before)
        a = _list_len(after)
        detail = f"Записей: {b} → {a}"
    else:
        detail = "Изменены настройки"
    return {
        "key": key,
        "label": label,
        "detail": detail,
        "before_summary": str(before)[:120] if before is not None else "—",
        "after_summary": str(after)[:120] if after is not None else "—",
    }


def compare_snapshots(before: dict, after: dict) -> dict:
    """Сводка отличий двух снимков capture_snapshot."""
    before = before or {}
    after = after or {}
    keys = sorted(set(before) | set(after))
    sections = []
    for key in keys:
        lv = before.get(key)
        rv = after.get(key)
        if lv == rv:
            continue
        sections.append(_summarize_change(key, lv, rv))
    return {
        "ok": True,
        "changed_sections": len(sections),
        "sections": sections,
        "unchanged": len(keys) - len(sections),
    }


def compare_snapshots_detailed(before: dict, after: dict) -> dict:
    """Сводка отличий + diff форм/BPM и политик между двумя снимками."""
    from delayu.services.config_diff import compare_policies
    from delayu.services.studio_admin import compare_restore_entity_diffs

    result = compare_snapshots(before, after)
    result["entity_diffs"] = compare_restore_entity_diffs(before or {}, after or {})
    result["policies_diff"] = compare_policies(
        (before or {}).get("policies") or {},
        (after or {}).get("policies") or {},
    )
    result["has_detail_changes"] = bool(
        result.get("changed_sections")
        or result["entity_diffs"].get("has_form_changes")
        or result["entity_diffs"].get("has_bpm_changes")
        or result["policies_diff"].get("changed")
    )
    return result
