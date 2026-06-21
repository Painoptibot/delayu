"""Архив: сроки хранения и очистка (M06)."""
from datetime import timedelta

from django.utils import timezone

from delayu.models import CaseFile, DataRetentionPolicy


def get_or_create_retention_policy(subsystem) -> DataRetentionPolicy:
    policy, _ = DataRetentionPolicy.objects.get_or_create(subsystem=subsystem)
    return policy


def default_archive_years(subsystem) -> int:
    try:
        return int(get_or_create_retention_policy(subsystem).default_archive_years)
    except Exception:
        return 5


def retention_alerts(subsystem, *, within_days: int | None = None):
    if within_days is None:
        within_days = get_or_create_retention_policy(subsystem).alert_days_before
    today = timezone.now().date()
    until = today + timedelta(days=within_days)
    return (
        CaseFile.objects.filter(
            subsystem=subsystem,
            is_archived=True,
            legal_hold=False,
            retention_until__isnull=False,
            retention_until__gte=today,
            retention_until__lte=until,
        )
        .select_related("assignee")
        .order_by("retention_until")[:20]
    )


def retention_expired(subsystem):
    today = timezone.now().date()
    return CaseFile.objects.filter(
        subsystem=subsystem,
        is_archived=True,
        legal_hold=False,
        retention_until__isnull=False,
        retention_until__lt=today,
    ).count()


def expired_cases_qs(subsystem):
    today = timezone.now().date()
    return CaseFile.objects.filter(
        subsystem=subsystem,
        is_archived=True,
        legal_hold=False,
        retention_until__isnull=False,
        retention_until__lt=today,
    ).order_by("retention_until")


def purge_expired_cases(subsystem, *, dry_run: bool = True) -> dict:
    """Удаление дел с истёкшим сроком хранения (без legal hold)."""
    qs = expired_cases_qs(subsystem)
    count = qs.count()
    numbers = list(qs.values_list("number", flat=True)[:20])
    if dry_run:
        return {"dry_run": True, "count": count, "sample": numbers}
    deleted, _details = qs.delete()
    return {"dry_run": False, "deleted": deleted, "count": count, "sample": numbers}
