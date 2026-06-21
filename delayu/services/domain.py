"""Доменные сервисы: транзакции и единая точка изменений."""
from functools import wraps

from django.db import transaction


def atomic_service(func):
    """Оборачивает сервисную функцию в transaction.atomic."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        with transaction.atomic():
            return func(*args, **kwargs)

    return wrapper


def scoped_queryset(model, subsystem, *, organization=None, extra=None):
    """Базовый queryset с фильтром подсистемы (и организации при наличии поля)."""
    qs = model.objects.filter(subsystem=subsystem)
    if organization is not None and hasattr(model, "organization_id"):
        qs = qs.filter(organization=organization)
    if extra:
        qs = qs.filter(**extra)
    return qs
