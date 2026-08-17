"""Land-use palette / legend for local MNP genplan layers."""
from __future__ import annotations

from typing import Any

# FGISTP-ish functional zones (classid → readable style).
_CLASS_STYLES: dict[str, dict[str, Any]] = {
    "701010101": {
        "label": "Жилая",
        "fill": "#4caf50",
        "stroke": "#2e7d32",
        "fill_rgba": (76, 175, 80, 110),
        "stroke_rgba": (46, 125, 50, 220),
    },
    "701010200": {
        "label": "Общественно-деловая",
        "fill": "#2196f3",
        "stroke": "#1565c0",
        "fill_rgba": (33, 150, 243, 110),
        "stroke_rgba": (21, 101, 192, 220),
    },
    "701010301": {
        "label": "Производственная",
        "fill": "#ff9800",
        "stroke": "#ef6c00",
        "fill_rgba": (255, 152, 0, 110),
        "stroke_rgba": (239, 108, 0, 220),
    },
    "701010401": {
        "label": "Инженерная инфраструктура",
        "fill": "#9c27b0",
        "stroke": "#6a1b9a",
        "fill_rgba": (156, 39, 176, 110),
        "stroke_rgba": (106, 27, 154, 220),
    },
    "701010500": {
        "label": "Транспортная",
        "fill": "#607d8b",
        "stroke": "#37474f",
        "fill_rgba": (96, 125, 139, 120),
        "stroke_rgba": (55, 71, 79, 230),
    },
    "701010600": {
        "label": "Сельскохозяйственная",
        "fill": "#cddc39",
        "stroke": "#9e9d24",
        "fill_rgba": (205, 220, 57, 100),
        "stroke_rgba": (158, 157, 36, 220),
    },
    "701010700": {
        "label": "Рекреационная",
        "fill": "#00bcd4",
        "stroke": "#00838f",
        "fill_rgba": (0, 188, 212, 100),
        "stroke_rgba": (0, 131, 143, 220),
    },
    "701010800": {
        "label": "Специального назначения",
        "fill": "#f44336",
        "stroke": "#c62828",
        "fill_rgba": (244, 67, 54, 100),
        "stroke_rgba": (198, 40, 40, 220),
    },
    "701010900": {
        "label": "Иная / прочее",
        "fill": "#795548",
        "stroke": "#4e342e",
        "fill_rgba": (121, 85, 72, 100),
        "stroke_rgba": (78, 52, 46, 220),
    },
}

_DEFAULT = {
    "label": "Зона генплана",
    "fill": "#7367f0",
    "stroke": "#5e50ee",
    "fill_rgba": (115, 103, 240, 100),
    "stroke_rgba": (94, 80, 238, 220),
}


def style_for_classid(classid: str | None) -> dict[str, Any]:
    key = str(classid or "").strip()
    if key in _CLASS_STYLES:
        return dict(_CLASS_STYLES[key])
    # Prefix match (subtype codes)
    for prefix, style in _CLASS_STYLES.items():
        if key.startswith(prefix[:7]):
            return dict(style)
    return dict(_DEFAULT)


def legend_items() -> list[dict[str, str]]:
    return [
        {"classid": cid, "label": style["label"], "fill": style["fill"], "stroke": style["stroke"]}
        for cid, style in _CLASS_STYLES.items()
    ]


def map_style_config() -> dict[str, Any]:
    return {
        "byClassid": {
            cid: {"label": s["label"], "fill": s["fill"], "stroke": s["stroke"]}
            for cid, s in _CLASS_STYLES.items()
        },
        "default": {"label": _DEFAULT["label"], "fill": _DEFAULT["fill"], "stroke": _DEFAULT["stroke"]},
        "legend": legend_items(),
    }
