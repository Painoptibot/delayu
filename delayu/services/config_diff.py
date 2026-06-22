"""Детальный diff меню, BPM, печатных форм и политик по ревизиям Студии."""
from __future__ import annotations

import re

_VAR_RE = re.compile(r"\{\{([^}]+)\}\}")

_MENU_ATTRS = ("section", "roles", "badge", "pinned")
_BPM_ATTRS = (
    "type",
    "label",
    "form_schema_code",
    "escalate_after_hours",
    "escalate_to_role",
)


def _flatten_menu(layout: list) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for sec in layout or []:
        if not isinstance(sec, dict):
            continue
        header = sec.get("header") or ""
        for it in sec.get("items") or []:
            if isinstance(it, str):
                url = it
                spec = {"url": url, "section": header, "roles": [], "badge": "", "pinned": False}
            else:
                url = it.get("url") or it.get("url_name") or ""
                spec = {
                    "url": url,
                    "section": header,
                    "roles": sorted(it.get("roles") or []),
                    "badge": it.get("badge") or "",
                    "pinned": bool(it.get("pinned")),
                }
            if url:
                out[url] = spec
    return out


def compare_menu_layouts(before: list, after: list) -> dict:
    bmap = _flatten_menu(before)
    amap = _flatten_menu(after)
    added = []
    removed = []
    changed = []
    for url, spec in amap.items():
        if url not in bmap:
            added.append({"url": url, "section": spec.get("section")})
            continue
        diffs = []
        for attr in _MENU_ATTRS:
            old = bmap[url].get(attr)
            new = spec.get(attr)
            if old != new:
                diffs.append({"attr": attr, "before": old, "after": new})
        if diffs:
            changed.append({"url": url, "diffs": diffs})
    for url, spec in bmap.items():
        if url not in amap:
            removed.append({"url": url, "section": spec.get("section")})
    return {
        "ok": True,
        "added": added,
        "removed": removed,
        "changed": changed,
        "unchanged": len(set(bmap) & set(amap)) - len(changed),
    }


def compare_correspondence_workflows(before: dict, after: dict) -> dict:
    before = before or {}
    after = after or {}
    b_steps = list(before.get("steps") or [])
    a_steps = list(after.get("steps") or [])
    b_sla = before.get("sla_days") or {}
    a_sla = after.get("sla_days") or {}

    added = [s for s in a_steps if s not in b_steps]
    removed = [s for s in b_steps if s not in a_steps]
    moved = []
    for step in set(b_steps) & set(a_steps):
        if b_steps.index(step) != a_steps.index(step):
            moved.append(
                {
                    "step": step,
                    "before_index": b_steps.index(step),
                    "after_index": a_steps.index(step),
                }
            )
    sla_changed = []
    for step in set(b_sla) | set(a_sla):
        old = b_sla.get(step)
        new = a_sla.get(step)
        if old != new:
            sla_changed.append({"step": step, "before": old, "after": new})
    return {
        "ok": True,
        "added_steps": added,
        "removed_steps": removed,
        "moved_steps": moved,
        "sla_changed": sla_changed,
        "steps_equal": b_steps == a_steps and not sla_changed,
    }


_POLICY_ATTRS = (
    "retention_years",
    "alert_days",
    "auto_purge",
    "siem_enabled",
    "siem_webhook",
)


def compare_policies(before: dict, after: dict) -> dict:
    before = before or {}
    after = after or {}
    changed = []
    for attr in _POLICY_ATTRS:
        old = before.get(attr)
        new = after.get(attr)
        if old != new:
            changed.append({"attr": attr, "before": old, "after": new})
    return {
        "ok": True,
        "changed": changed,
        "unchanged": len(_POLICY_ATTRS) - len(changed),
    }


def _index_bpm_nodes(diagram: dict) -> dict[str, dict]:
    nodes = (diagram or {}).get("nodes") or []
    return {n["id"]: n for n in nodes if isinstance(n, dict) and n.get("id")}


def compare_bpm_templates(before: dict, after_diagram: dict) -> dict:
    """Сравнение BPM-шаблона: before — строка из snapshot, after — текущий diagram."""
    bmap = _index_bpm_nodes((before or {}).get("diagram") or {})
    amap = _index_bpm_nodes(after_diagram or {})
    added = []
    removed = []
    changed = []
    for nid, spec in amap.items():
        if nid not in bmap:
            added.append({"id": nid, "label": spec.get("label") or spec.get("type")})
            continue
        diffs = []
        for attr in _BPM_ATTRS:
            old = bmap[nid].get(attr)
            new = spec.get(attr)
            if old != new:
                diffs.append({"attr": attr, "before": old, "after": new})
        if diffs:
            changed.append({"id": nid, "label": spec.get("label") or nid, "diffs": diffs})
    for nid, spec in bmap.items():
        if nid not in amap:
            removed.append({"id": nid, "label": spec.get("label") or spec.get("type")})
    bedges = (before or {}).get("diagram") or {}
    aedges = after_diagram or {}
    edge_change = len((bedges.get("edges") or [])) != len((aedges.get("edges") or []))
    return {
        "ok": True,
        "added": added,
        "removed": removed,
        "changed": changed,
        "edges_changed": edge_change,
        "unchanged": len(set(bmap) & set(amap)) - len(changed),
    }


def _normalize_print_body(html: str) -> str:
    return re.sub(r"\s+", " ", html or "").strip()


def compare_print_templates(before: dict, after_body: str) -> dict:
    """Сравнение печатной формы: before — строка из snapshot, after_body — текущий HTML."""
    before_body = (before or {}).get("body") or ""
    after_body = after_body or ""
    bvars = set(_VAR_RE.findall(before_body))
    avars = set(_VAR_RE.findall(after_body))
    return {
        "ok": True,
        "body_changed": _normalize_print_body(before_body) != _normalize_print_body(after_body),
        "added_variables": sorted(avars - bvars),
        "removed_variables": sorted(bvars - avars),
        "size_before": len(before_body),
        "size_after": len(after_body),
    }


_NSI_META_ATTRS = ("name", "description", "is_active")
_INT_META_ATTRS = ("endpoint_type", "is_active", "max_retries")
_SMEV_ATTRS = ("transport", "url", "test_mode", "client_id")


def compare_nsi_classifier(before: dict, after_values: list, *, after_meta: dict | None = None) -> dict:
    """Сравнение справочника НСИ: метаданные и порядок/состав значений."""
    before = before or {}
    after_meta = after_meta or {}
    changed_meta = []
    for attr in _NSI_META_ATTRS:
        old = before.get(attr)
        new = after_meta.get(attr)
        if new is not None and old != new:
            changed_meta.append({"attr": attr, "before": old, "after": new})
    b_vals = before.get("values") or []
    a_vals = after_values or []
    b_codes = [v.get("code") for v in b_vals if v.get("code")]
    a_codes = [v.get("code") for v in a_vals if v.get("code")]
    added = [c for c in a_codes if c not in b_codes]
    removed = [c for c in b_codes if c not in a_codes]
    renamed = []
    bmap = {v.get("code"): v.get("name") for v in b_vals if v.get("code")}
    amap = {v.get("code"): v.get("name") for v in a_vals if v.get("code")}
    for code in set(bmap) & set(amap):
        if bmap[code] != amap[code]:
            renamed.append({"code": code, "before": bmap[code], "after": amap[code]})
    reordered = b_codes != a_codes and not added and not removed
    return {
        "ok": True,
        "meta_changed": changed_meta,
        "added_values": added,
        "removed_values": removed,
        "renamed_values": renamed,
        "reordered": reordered,
    }


def compare_integration_endpoint(before: dict, after: dict) -> dict:
    """Сравнение endpoint интеграции: метаданные, pipeline и СМЭВ-транспорт."""
    before = before or {}
    after = after or {}
    changed_meta = []
    for attr in _INT_META_ATTRS:
        old = before.get(attr)
        new = after.get(attr)
        if new is not None and old != new:
            changed_meta.append({"attr": attr, "before": old, "after": new})
    bcfg = before.get("config") or {}
    acfg = after.get("config") or {}
    b_nodes = ((bcfg.get("pipeline") or {}).get("nodes") or [])
    a_nodes = ((acfg.get("pipeline") or {}).get("nodes") or [])
    b_types = [n.get("type") for n in b_nodes if isinstance(n, dict)]
    a_types = [n.get("type") for n in a_nodes if isinstance(n, dict)]
    pipeline_changed = b_types != a_types
    smev_changed = []
    for attr in _SMEV_ATTRS:
        old = bcfg.get(attr)
        new = acfg.get(attr)
        if old != new:
            smev_changed.append({"attr": attr, "before": old, "after": new})
    return {
        "ok": True,
        "meta_changed": changed_meta,
        "pipeline_changed": pipeline_changed,
        "pipeline_before": len(b_nodes),
        "pipeline_after": len(a_nodes),
        "smev_changed": smev_changed,
    }
