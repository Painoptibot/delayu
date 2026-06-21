"""Единый реестр объектов платформы (#7) — поиск и deep-link."""
from django.db.models import Q

from delayu.models import CaseFile, Correspondence, DocumentFile, TaskItem


OBJECT_TYPES = {
    "case": {"model": CaseFile, "label": "Дело", "url": "platform-case-detail"},
    "task": {"model": TaskItem, "label": "Задача", "url": "platform-task-edit"},
    "correspondence": {"model": Correspondence, "label": "Корреспонденция", "url": "platform-correspondence-detail"},
    "document": {"model": DocumentFile, "label": "Документ", "url": "platform-documents"},
}


def global_search(subsystem, query: str, *, limit: int = 20, user=None):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    if getattr(subsystem, "industry_template", None) == "uzhv":
        from delayu.services.uzhv_search import uzhv_global_search

        return uzhv_global_search(subsystem, q, limit=limit, user=user)
    results = []
    for kind, meta in OBJECT_TYPES.items():
        model = meta["model"]
        qs = model.objects.filter(subsystem=subsystem)
        if kind == "case":
            qs = qs.filter(Q(number__icontains=q) | Q(title__icontains=q))
        elif kind == "task":
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        elif kind == "correspondence":
            qs = qs.filter(
                Q(reg_number__icontains=q) | Q(subject__icontains=q) | Q(counterparty__icontains=q)
            )
        elif kind == "document":
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        for obj in qs[: limit // len(OBJECT_TYPES) + 1]:
            entry = {
                "type": kind,
                "type_label": meta["label"],
                "id": obj.pk,
                "title": _object_title(kind, obj),
                "url_name": meta["url"],
            }
            results.append(entry)
        if len(results) >= limit:
            break
    return results[:limit]


def _object_title(kind, obj) -> str:
    if kind == "case":
        return f"{obj.number} — {obj.title}"
    if kind == "task":
        return obj.title
    if kind == "correspondence":
        return f"{obj.reg_number} — {obj.subject}"
    if kind == "document":
        return obj.title or obj.description or str(obj.pk)
    return str(obj)
