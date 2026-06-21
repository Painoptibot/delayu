"""Поисковый индекс: rebuild + гибридный query + эмбеддинги."""
from __future__ import annotations

import hashlib
import re

from django.db.models import Q

from delayu.models import CaseFile, DocumentFile, KnowledgeArticle, SearchIndexEntry
from delayu.services.embeddings import cosine_similarity, embed_text
from delayu.services.pgvector_search import pgvector_available, semantic_search, sync_entry_vector

_TOKEN_SPLIT = re.compile(r"\W+")


def _content_hash(title: str, body: str) -> str:
    payload = f"{title}\n{body}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _index_row(*, subsystem, kind: str, object_id: int, title: str, body: str = ""):
    h = _content_hash(title, body)
    text = f"{title}\n{body}"
    vector = embed_text(text)
    entry, created = SearchIndexEntry.objects.get_or_create(
        subsystem=subsystem,
        kind=kind,
        object_id=object_id,
        defaults={
            "title": title[:500],
            "body": body,
            "content_hash": h,
            "embedding": vector,
        },
    )
    if not created and entry.content_hash == h and entry.embedding:
        sync_entry_vector(entry.pk, entry.embedding)
        return entry
    entry.title = title[:500]
    entry.body = body
    entry.content_hash = h
    entry.embedding = vector
    entry.save(update_fields=["title", "body", "content_hash", "embedding", "indexed_at"])
    sync_entry_vector(entry.pk, vector)
    return entry


def rebuild_search_index(subsystem) -> dict:
    counts = {"case": 0, "knowledge": 0, "document": 0, "embeddings": 0}
    for case in CaseFile.objects.filter(subsystem=subsystem, is_archived=False):
        _index_row(
            subsystem=subsystem,
            kind="case",
            object_id=case.pk,
            title=f"{case.number} {case.title}",
            body=case.description or "",
        )
        counts["case"] += 1
    for art in KnowledgeArticle.objects.filter(subsystem=subsystem, is_published=True):
        _index_row(
            subsystem=subsystem,
            kind="knowledge",
            object_id=art.pk,
            title=art.title,
            body=art.body or "",
        )
        counts["knowledge"] += 1
    for doc in DocumentFile.objects.filter(subsystem=subsystem, is_current=True):
        _index_row(
            subsystem=subsystem,
            kind="document",
            object_id=doc.pk,
            title=doc.title,
            body=doc.description or "",
        )
        counts["document"] += 1
    counts["embeddings"] = SearchIndexEntry.objects.filter(subsystem=subsystem).exclude(embedding=[]).count()
    return counts


def _score_text(query: str, title: str, body: str) -> float:
    q = query.lower().strip()
    text = f"{title} {body}".lower()
    if q in text:
        return 1.0
    tokens = [t for t in _TOKEN_SPLIT.split(q) if len(t) > 2]
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in text)
    return hits / len(tokens)


def search_index(subsystem, query: str, *, limit: int = 15) -> list[dict]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    query_vec = embed_text(q)
    if pgvector_available():
        pg_hits = semantic_search(subsystem.pk, query_vec, limit=limit)
        if pg_hits:
            return pg_hits
    qs = SearchIndexEntry.objects.filter(subsystem=subsystem).filter(
        Q(title__icontains=q) | Q(body__icontains=q)
    )
    if qs.count() < 5:
        qs = SearchIndexEntry.objects.filter(subsystem=subsystem)[:300]
    else:
        qs = qs[:200]
    results = []
    for row in qs:
        token_score = _score_text(q, row.title, row.body)
        emb_score = cosine_similarity(query_vec, row.embedding or [])
        score = max(token_score, emb_score)
        if score < 0.34:
            continue
        results.append(
            {
                "type": row.kind,
                "id": row.object_id,
                "title": row.title[:255],
                "score": round(score, 2),
                "semantic": emb_score >= token_score,
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit]
