"""Валидация JSON-пакетов конфигурации Студии перед импортом."""
from __future__ import annotations

_CODED_LISTS = ("forms", "bpm", "print", "nsi", "integrations")
_SNAPSHOT_KEYS = (
    "menu_layout",
    "correspondence_workflow",
    "forms",
    "bpm",
    "print",
    "nsi",
    "integrations",
    "role_layouts",
    "policies",
)


def validate_config_package(package: dict) -> dict:
    """Проверка структуры пакета delayu-studio-package."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(package, dict):
        return {"ok": False, "valid": False, "errors": ["Пакет должен быть JSON-объектом"], "warnings": []}

    fmt = package.get("format")
    if fmt and fmt != "delayu-studio-package":
        errors.append(f"Неизвестный format: {fmt}")
    version = package.get("format_version")
    if version is not None and version != 1:
        warnings.append(f"Версия формата {version} может быть несовместима")

    snap = package.get("snapshot")
    if snap is None:
        if any(k in package for k in _SNAPSHOT_KEYS):
            snap = package
        else:
            errors.append("Отсутствует snapshot")
            snap = {}

    if snap and not isinstance(snap, dict):
        errors.append("snapshot должен быть объектом")
        snap = {}

    if snap:
        if snap.get("menu_layout") is not None and not isinstance(snap["menu_layout"], list):
            errors.append("menu_layout должен быть списком")
        if snap.get("correspondence_workflow") is not None and not isinstance(
            snap["correspondence_workflow"], dict
        ):
            errors.append("correspondence_workflow должен быть объектом")
        if snap.get("policies") is not None and not isinstance(snap["policies"], dict):
            errors.append("policies должен быть объектом")

        for key in _CODED_LISTS:
            rows = snap.get(key)
            if rows is None:
                continue
            if not isinstance(rows, list):
                errors.append(f"{key} должен быть списком")
                continue
            for idx, row in enumerate(rows):
                if not isinstance(row, dict):
                    errors.append(f"{key}[{idx}]: ожидается объект")
                    continue
                if not (row.get("code") or "").strip():
                    errors.append(f"{key}[{idx}]: отсутствует code")

        layouts = snap.get("role_layouts")
        if layouts is not None:
            if not isinstance(layouts, list):
                errors.append("role_layouts должен быть списком")
            else:
                for idx, row in enumerate(layouts):
                    if not isinstance(row, dict):
                        errors.append(f"role_layouts[{idx}]: ожидается объект")
                        continue
                    if not row.get("role_code") and not row.get("role_id"):
                        warnings.append(f"role_layouts[{idx}]: нет role_code/role_id")

        if not any(snap.get(k) is not None for k in _SNAPSHOT_KEYS):
            warnings.append("Снимок не содержит известных секций конфигурации")

    draft = package.get("studio_draft")
    if draft is not None and not isinstance(draft, dict):
        errors.append("studio_draft должен быть объектом")

    return {
        "ok": len(errors) == 0,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def validate_blueprint_package(package: dict) -> dict:
    """Проверка JSON шаблона delayu-blueprint."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(package, dict):
        return {"ok": False, "valid": False, "errors": ["Шаблон должен быть JSON-объектом"], "warnings": []}

    fmt = package.get("format")
    bp = package.get("blueprint") if fmt == "delayu-blueprint" else package
    if not isinstance(bp, dict):
        errors.append("Отсутствует blueprint")
        bp = {}

    if fmt and fmt != "delayu-blueprint":
        errors.append(f"Неизвестный format: {fmt}")

    blueprint_id = (bp.get("id") or "").strip()
    if not blueprint_id:
        warnings.append("Нет id шаблона (будет импортирован как custom)")

    name = bp.get("name")
    if name is not None and not isinstance(name, str):
        errors.append("name должен быть строкой")

    menu = bp.get("menu")
    if menu is not None:
        if not isinstance(menu, list):
            errors.append("menu должен быть списком секций")
        else:
            for idx, sec in enumerate(menu):
                if not isinstance(sec, dict):
                    errors.append(f"menu[{idx}]: ожидается объект секции")
                    continue
                items = sec.get("items")
                if items is not None and not isinstance(items, list):
                    errors.append(f"menu[{idx}].items должен быть списком")

    corr = bp.get("correspondence")
    if corr is not None:
        if not isinstance(corr, dict):
            errors.append("correspondence должен быть объектом")
        elif corr.get("steps") is not None and not isinstance(corr["steps"], list):
            errors.append("correspondence.steps должен быть списком")

    layouts = bp.get("role_layouts")
    if layouts is not None:
        if not isinstance(layouts, list):
            errors.append("role_layouts должен быть списком")
        else:
            for idx, row in enumerate(layouts):
                if not isinstance(row, dict):
                    errors.append(f"role_layouts[{idx}]: ожидается объект")
                    continue
                if not row.get("role_code"):
                    errors.append(f"role_layouts[{idx}]: отсутствует role_code")
                if not row.get("kind"):
                    warnings.append(f"role_layouts[{idx}]: нет kind")
                widgets = row.get("widgets")
                if widgets is not None and not isinstance(widgets, list):
                    errors.append(f"role_layouts[{idx}].widgets должен быть списком")

    if not any(bp.get(k) for k in ("menu", "correspondence", "role_layouts")):
        warnings.append("Шаблон не содержит menu, correspondence или role_layouts")

    return {
        "ok": len(errors) == 0,
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "blueprint_id": blueprint_id,
    }
