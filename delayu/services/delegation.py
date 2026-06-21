"""Делегирование полномочий между сотрудниками."""
from django.utils import timezone

from delayu.models import Delegation


def _today():
    return timezone.now().date()


def active_delegations_qs(*, subsystem, user=None, direction="received"):
    today = _today()
    qs = Delegation.objects.filter(
        subsystem=subsystem,
        is_active=True,
        start_at__lte=today,
        end_at__gte=today,
    ).select_related("from_user", "to_user")
    if direction == "received" and user:
        qs = qs.filter(to_user=user)
    elif direction == "given" and user:
        qs = qs.filter(from_user=user)
    return qs.order_by("-start_at")


def delegation_principals(user, subsystem) -> list[int]:
    """Пользователи, чьи дела доступны делегату."""
    return list(
        active_delegations_qs(subsystem=subsystem, user=user, direction="received").values_list(
            "from_user_id", flat=True
        )
    )


def create_delegation(*, subsystem, from_user, to_user, start_at, end_at):
    if from_user.pk == to_user.pk:
        raise ValueError("Нельзя делегировать самому себе")
    if end_at < start_at:
        raise ValueError("Дата окончания раньше начала")
    return Delegation.objects.create(
        subsystem=subsystem,
        from_user=from_user,
        to_user=to_user,
        start_at=start_at,
        end_at=end_at,
        is_active=True,
    )


def revoke_delegation(delegation: Delegation) -> None:
    delegation.is_active = False
    delegation.save(update_fields=["is_active"])
