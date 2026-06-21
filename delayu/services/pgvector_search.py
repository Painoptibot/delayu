"""PostgreSQL pgvector: нативный семантический поиск (fallback — JSON + Python)."""
from __future__ import annotations

from django.db import connection

from delayu.services.embeddings import _DIM


def pgvector_available() -> bool:
    if connection.vendor != "postgresql":
        return False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            return cursor.fetchone() is not None
    except Exception:
        return False


def _column_exists(cursor, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'delayu_searchindexentry' AND column_name = %s
        """,
        [column],
    )
    return cursor.fetchone() is not None


def ensure_pgvector_schema(*, dims: int = _DIM) -> bool:
    """CREATE EXTENSION + колонка embedding_vec (идемпотентно, только PostgreSQL)."""
    if connection.vendor != "postgresql":
        return False
    try:
        with connection.cursor() as cursor:
            try:
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except Exception:
                return False
            if not _column_exists(cursor, "embedding_vec"):
                cursor.execute(
                    f"ALTER TABLE delayu_searchindexentry ADD COLUMN embedding_vec vector({dims})"
                )
            try:
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS delayu_searchindexentry_embedding_vec_idx
                    ON delayu_searchindexentry
                    USING ivfflat (embedding_vec vector_cosine_ops)
                    WITH (lists = 32)
                    """
                )
            except Exception:
                pass
        return pgvector_available()
    except Exception:
        return False


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(str(v) for v in vec) + "]"


def sync_entry_vector(entry_id: int, vector: list[float]) -> None:
    if not vector or not pgvector_available():
        return
    if not _column_exists_on_table():
        return
    literal = _vector_literal(vector)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE delayu_searchindexentry SET embedding_vec = %s::vector WHERE id = %s",
            [literal, entry_id],
        )


def _column_exists_on_table() -> bool:
    try:
        with connection.cursor() as cursor:
            return _column_exists(cursor, "embedding_vec")
    except Exception:
        return False


def semantic_search(subsystem_id: int, query_vec: list[float], *, limit: int = 15) -> list[dict]:
    if not query_vec or not pgvector_available() or not _column_exists_on_table():
        return []
    literal = _vector_literal(query_vec)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT kind, object_id, title,
                   GREATEST(0, 1 - (embedding_vec <=> %s::vector)) AS score
            FROM delayu_searchindexentry
            WHERE subsystem_id = %s AND embedding_vec IS NOT NULL
            ORDER BY embedding_vec <=> %s::vector
            LIMIT %s
            """,
            [literal, subsystem_id, literal, limit],
        )
        rows = cursor.fetchall()
    return [
        {
            "type": kind,
            "id": object_id,
            "title": (title or "")[:255],
            "score": round(float(score), 2),
            "semantic": True,
        }
        for kind, object_id, title, score in rows
        if score >= 0.34
    ]
