"""Пофieldный diff схем FormSchema."""
from __future__ import annotations

_DIFF_ATTRS = (
    "label",
    "type",
    "required",
    "section",
    "nsi_classifier",
    "registry_code",
    "lookup_label_field",
    "visible_when",
    "fill_map",
)


def _index_schema(schema: list) -> dict[str, dict]:
    return {f["key"]: f for f in schema or [] if isinstance(f, dict) and f.get("key")}


def compare_form_schemas(before: list, after: list) -> dict:
    """Сравнение двух списков полей схемы."""
    bmap = _index_schema(before)
    amap = _index_schema(after)
    added = []
    removed = []
    changed = []
    for key, spec in amap.items():
        if key not in bmap:
            added.append({"key": key, "label": spec.get("label") or key, "type": spec.get("type")})
            continue
        diffs = []
        for attr in _DIFF_ATTRS:
            old = bmap[key].get(attr)
            new = spec.get(attr)
            if old != new:
                diffs.append({"attr": attr, "before": old, "after": new})
        if diffs:
            changed.append({"key": key, "label": spec.get("label") or key, "diffs": diffs})
    for key, spec in bmap.items():
        if key not in amap:
            removed.append({"key": key, "label": spec.get("label") or key, "type": spec.get("type")})
    by_section = _group_form_diff_by_section(added, removed, changed, bmap, amap)
    return {
        "ok": True,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(set(bmap) & set(amap)) - len(changed),
        "by_section": by_section,
    }


def _section_label(spec: dict | None) -> str:
    if not spec:
        return "—"
    sec = spec.get("section")
    return sec if sec else "Без секции"


def _group_form_diff_by_section(
    added: list,
    removed: list,
    changed: list,
    bmap: dict,
    amap: dict,
) -> dict:
    """Группировка diff по секциям формы."""
    sections: dict[str, dict] = {}

    def bucket(section: str) -> dict:
        if section not in sections:
            sections[section] = {"added": [], "removed": [], "changed": []}
        return sections[section]

    for item in added:
        sec = _section_label(amap.get(item["key"]))
        bucket(sec)["added"].append(item)
    for item in removed:
        sec = _section_label(bmap.get(item["key"]))
        bucket(sec)["removed"].append(item)
    for item in changed:
        sec = _section_label(amap.get(item["key"]) or bmap.get(item["key"]))
        bucket(sec)["changed"].append(item)
    return sections
