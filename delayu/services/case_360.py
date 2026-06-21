"""M22 — единая карточка дела 360°: связи, задачи, хронология."""
from __future__ import annotations

from delayu.models import (
    ActivityEvent,
    AuditLog,
    BPMInstance,
    BPMTask,
    CaseFile,
    Comment,
    Correspondence,
    TaskItem,
)


def _actor_label(user) -> str:
    if not user:
        return "—"
    return user.get_full_name() or user.get_username()


def build_case_timeline(case: CaseFile, *, limit: int = 80) -> list[dict]:
    """Объединённая лента: аудит, активность, комментарии, BPM, корреспонденция."""
    case_id = str(case.pk)
    link_needle = f"/cases/{case.pk}"
    events: list[dict] = []

    for row in AuditLog.objects.filter(
        subsystem=case.subsystem, model_name="CaseFile", object_id=case_id
    ).select_related("user")[: limit // 2]:
        events.append(
            {
                "kind": "audit",
                "at": row.created_at,
                "actor": row.user,
                "title": row.action,
                "detail": row.model_name,
            }
        )

    for row in ActivityEvent.objects.filter(
        subsystem=case.subsystem, link_path__icontains=link_needle
    ).select_related("actor")[: limit // 2]:
        events.append(
            {
                "kind": "activity",
                "at": row.created_at,
                "actor": row.actor,
                "title": row.verb,
                "detail": row.target_repr,
                "link": row.link_path or "",
            }
        )

    for row in Comment.objects.filter(case=case).select_related("author")[:20]:
        events.append(
            {
                "kind": "comment",
                "at": row.created_at,
                "actor": row.author,
                "title": "Комментарий",
                "detail": (row.body or "")[:200],
            }
        )

    for row in BPMTask.objects.filter(instance__case=case, decided_at__isnull=False).select_related(
        "assignee", "instance__template"
    )[:20]:
        events.append(
            {
                "kind": "bpm",
                "at": row.decided_at,
                "actor": row.assignee,
                "title": f"BPM: {row.get_status_display()}",
                "detail": row.step_name,
            }
        )

    for row in Correspondence.objects.filter(case=case, is_deleted=False).select_related(
        "created_by"
    )[:20]:
        events.append(
            {
                "kind": "correspondence",
                "at": row.created_at,
                "actor": row.created_by,
                "title": f"Корреспонденция {row.reg_number}",
                "detail": row.subject[:200],
            }
        )

    events.sort(key=lambda item: item["at"] or case.created_at, reverse=True)
    for item in events:
        item["actor_label"] = _actor_label(item.get("actor"))
    return events[:limit]


def build_case_link_graph(case: CaseFile) -> dict:
    """#30 — граф связей дела с корреспонденцией, документами, задачами, BPM."""
    nodes = [
        {
            "id": f"case:{case.pk}",
            "label": case.number,
            "type": "case",
            "url": f"/cases/{case.pk}/",
        }
    ]
    edges: list[dict] = []
    seen = {f"case:{case.pk}"}

    def add_node(node_id, label, ntype, url=""):
        if node_id not in seen:
            nodes.append({"id": node_id, "label": label, "type": ntype, "url": url})
            seen.add(node_id)

    for c in Correspondence.objects.filter(case=case, is_deleted=False).order_by("-reg_date")[:20]:
        nid = f"corr:{c.pk}"
        add_node(nid, c.reg_number, "correspondence", f"/correspondence/{c.pk}/")
        edges.append({"from": f"case:{case.pk}", "to": nid, "label": c.get_direction_display()})

    for d in case.documents.filter(is_current=True).order_by("-created_at")[:20]:
        nid = f"doc:{d.pk}"
        add_node(nid, d.title[:40], "document", f"/documents/?open={d.pk}")
        edges.append({"from": f"case:{case.pk}", "to": nid, "label": "документ"})

    for t in TaskItem.objects.filter(case=case).order_by("-created_at")[:15]:
        nid = f"task:{t.pk}"
        add_node(nid, t.title[:40], "task", f"/workspace/tasks/{t.pk}/")
        edges.append({"from": f"case:{case.pk}", "to": nid, "label": "задача"})

    for inst in BPMInstance.objects.filter(case=case).select_related("template")[:10]:
        nid = f"bpm:{inst.pk}"
        add_node(nid, inst.template.name[:40], "bpm", f"/bpm/instances/{inst.pk}/")
        edges.append({"from": f"case:{case.pk}", "to": nid, "label": "BPM"})

    return {"nodes": nodes, "edges": edges, "count": len(edges)}


def build_case_360_context(case: CaseFile) -> dict:
    tasks = TaskItem.objects.filter(case=case).select_related("assignee").order_by(
        "-created_at"
    )
    correspondence = (
        Correspondence.objects.filter(case=case, is_deleted=False)
        .select_related("assignee", "created_by")
        .order_by("-reg_date")
    )
    bpm_instances = BPMInstance.objects.filter(case=case).select_related("template").order_by(
        "-started_at"
    )
    audit_slice = AuditLog.objects.filter(
        subsystem=case.subsystem,
        model_name="CaseFile",
        object_id=str(case.pk),
    ).select_related("user")[:15]
    timeline = build_case_timeline(case)
    open_tasks = tasks.filter(completed_at__isnull=True).count()
    link_graph = build_case_link_graph(case)
    return {
        "tasks": tasks,
        "open_tasks": open_tasks,
        "correspondence": correspondence,
        "corr_count": correspondence.count(),
        "bpm_instances": bpm_instances,
        "audit_slice": audit_slice,
        "timeline": timeline,
        "link_graph": link_graph,
        "stats": {
            "documents": case.documents.filter(is_current=True).count(),
            "tasks_open": open_tasks,
            "tasks_total": tasks.count(),
            "comments": case.comments.count(),
            "correspondence": correspondence.count(),
            "bpm_running": bpm_instances.filter(status=BPMInstance.Status.RUNNING).count(),
        },
    }
