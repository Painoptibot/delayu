"""Массовые операции с dry-run (#50)."""
from django.db.models import QuerySet


def dry_run_summary(qs: QuerySet, *, action: str) -> dict:
    count = qs.count()
    sample = list(qs.values("pk")[:5])
    return {
        "action": action,
        "count": count,
        "sample_ids": [r["pk"] for r in sample],
        "dry_run": True,
        "message": f"Будет затронуто записей: {count}",
    }
