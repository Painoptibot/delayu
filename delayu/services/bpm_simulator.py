"""Симулятор BPM-диаграммы Студии — прогон тестового маршрута."""
from __future__ import annotations

DEFAULT_TASK_HOURS = 8


def simulate_diagram(diagram: dict, *, hours_per_task: int = DEFAULT_TASK_HOURS) -> dict:
    nodes = {n["id"]: n for n in (diagram or {}).get("nodes") or []}
    edges = (diagram or {}).get("edges") or []
    if not nodes:
        return {"ok": False, "error": "empty", "timeline": [], "total_hours": 0, "total_days": 0}

    start = next((n for n in nodes.values() if n.get("type") == "start"), None)
    if not start:
        return {"ok": False, "error": "no_start", "timeline": [], "total_hours": 0, "total_days": 0}

    timeline: list[dict] = []
    elapsed = 0
    seen: set[str] = set()
    queue = [start["id"]]

    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        node = nodes.get(nid) or {}
        ntype = node.get("type") or "task"
        label = node.get("label") or nid

        if ntype == "start":
            timeline.append(
                {
                    "node_id": nid,
                    "type": ntype,
                    "label": label,
                    "elapsed_hours": 0,
                    "step_hours": 0,
                    "status": "done",
                }
            )
        elif ntype == "end":
            timeline.append(
                {
                    "node_id": nid,
                    "type": ntype,
                    "label": label,
                    "elapsed_hours": elapsed,
                    "step_hours": 0,
                    "status": "done",
                }
            )
            break
        elif ntype == "timer":
            step = int(node.get("sla_hours") or (node.get("sla_days") or 1) * 24)
            elapsed += max(step, 1)
            timeline.append(
                {
                    "node_id": nid,
                    "type": ntype,
                    "label": label,
                    "elapsed_hours": elapsed,
                    "step_hours": step,
                    "status": "sla",
                }
            )
        else:
            step = int(node.get("duration_hours") or hours_per_task)
            esc_after = int(node.get("escalate_after_hours") or 0)
            esc_role = node.get("escalate_to_role") or ""
            if esc_after and step > esc_after:
                timeline.append(
                    {
                        "node_id": nid,
                        "type": ntype,
                        "label": label,
                        "elapsed_hours": elapsed + esc_after,
                        "step_hours": esc_after,
                        "status": "active",
                    }
                )
                elapsed += esc_after
                timeline.append(
                    {
                        "node_id": nid,
                        "type": "escalation",
                        "label": f"Эскалация → {esc_role or 'руководитель'}",
                        "elapsed_hours": elapsed,
                        "step_hours": max(step - esc_after, 1),
                        "status": "escalated",
                        "escalate_to_role": esc_role,
                    }
                )
                elapsed += max(step - esc_after, 1)
            else:
                elapsed += max(step, 1)
                timeline.append(
                    {
                        "node_id": nid,
                        "type": ntype,
                        "label": label,
                        "elapsed_hours": elapsed,
                        "step_hours": step,
                        "status": "active",
                    }
                )

        for edge in edges:
            if edge.get("from") == nid:
                nxt = edge.get("to")
                if nxt and nxt not in seen:
                    queue.append(nxt)

    return {
        "ok": True,
        "total_hours": elapsed,
        "total_days": round(elapsed / 24, 1),
        "timeline": timeline,
        "highlight_ids": [t["node_id"] for t in timeline],
    }
