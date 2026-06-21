"""Жилконтроль: синхронизация статусов предписаний."""
from django.utils import timezone

from delayu.models_uzhv import HousingPrescription


def sync_overdue_prescriptions(subsystem) -> int:
    """Помечает просроченные предписания статусом OVERDUE. Возвращает число обновлённых."""
    today = timezone.now().date()
    qs = HousingPrescription.objects.filter(
        inspection__subsystem=subsystem,
        due_date__lt=today,
    ).exclude(
        status__in=[
            HousingPrescription.Status.FULFILLED,
            HousingPrescription.Status.CANCELLED,
            HousingPrescription.Status.OVERDUE,
        ]
    )
    return qs.update(status=HousingPrescription.Status.OVERDUE)
