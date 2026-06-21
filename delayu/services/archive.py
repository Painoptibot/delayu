from datetime import timedelta

from django.utils import timezone

from delayu.models import CaseFile


def archive_case(case: CaseFile, user, *, reason: str = "", retention_years: int | None = 5):
    from delayu.services.retention import default_archive_years

    if retention_years is None:
        retention_years = default_archive_years(case.subsystem)
    """Перевод дела в архив: статус, срок хранения (по умолчанию 5 лет), кто архивировал."""
    case.status = CaseFile.Status.ARCHIVED
    case.is_archived = True
    case.archived_at = timezone.now()
    case.archived_by = user
    case.archive_reason = (reason or "")[:4000]
    if retention_years is not None and retention_years > 0:
        case.retention_until = timezone.now().date() + timedelta(days=365 * int(retention_years))
    else:
        case.retention_until = None
    case.save(
        update_fields=[
            "status",
            "is_archived",
            "archived_at",
            "archived_by",
            "archive_reason",
            "retention_until",
            "updated_at",
        ]
    )
    return case


def restore_case(case: CaseFile, user):
    """Восстановление из архива (оформленное); при legal hold — ошибка."""
    if case.legal_hold:
        raise ValueError("Снятите legal hold перед восстановлением дела.")
    case.is_archived = False
    case.status = CaseFile.Status.DONE
    case.archived_at = None
    case.archived_by = None
    case.archive_reason = ""
    case.retention_until = None
    case.save(
        update_fields=[
            "is_archived",
            "status",
            "archived_at",
            "archived_by",
            "archive_reason",
            "retention_until",
            "updated_at",
        ]
    )
    return case


def set_legal_hold(case: CaseFile, value: bool):
    case.legal_hold = value
    case.save(update_fields=["legal_hold", "updated_at"])
    return case
