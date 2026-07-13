"""Подсказки марок и моделей ТС для формы заявки."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CYR_TO_LAT = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ",
    "abvgdeejzijklmnoprstufhzcss_y_euaABVGDEEJZIJKLMNOPRSTUFHZCSS_Y_EUA",
)


def _normalize_query(raw: str) -> str:
    q = (raw or "").strip().lower().translate(CYR_TO_LAT)
    return re.sub(r"[^a-z0-9]+", "", q)


@lru_cache(maxsize=1)
def _vehicle_catalog() -> tuple[str, ...]:
    path = Path(__file__).resolve().parent.parent / "data" / "fuel_vehicles.json"
    with path.open(encoding="utf-8") as fh:
        items = json.load(fh)
    return tuple(dict.fromkeys(str(x).strip() for x in items if str(x).strip()))


def suggest_vehicles(query: str, *, limit: int = 8) -> list[str]:
    q = _normalize_query(query)
    if len(q) < 3:
        return []
    catalog = _vehicle_catalog()
    starts = []
    contains = []
    for item in catalog:
        hay = _normalize_query(item)
        if hay.startswith(q):
            starts.append(item)
        elif q in hay:
            contains.append(item)
    result = starts + contains
    return result[:limit]
