from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestRoadmapItem

DEFAULT_SUPPORT_STEPS: list[tuple[str, str, int]] = [
    ("land", "Земля", 14),
    ("permits", "Разрешения", 45),
    ("build", "Строительство", 180),
    ("commission", "Ввод в эксплуатацию", 365),
]


@transaction.atomic
def seed_support_roadmap(project) -> list[InvestRoadmapItem]:
    existing = list(project.roadmap_items.order_by("due_at", "code"))
    if existing:
        return existing
    now = timezone.now()
    items = [
        InvestRoadmapItem(
            project=project,
            code=code,
            title=title,
            due_at=now + timedelta(days=days),
            status=InvestRoadmapItem.Status.OPEN,
        )
        for code, title, days in DEFAULT_SUPPORT_STEPS
    ]
    return InvestRoadmapItem.objects.bulk_create(items)


def overdue_items(*, subsystem):
    now = timezone.now()
    return InvestRoadmapItem.objects.filter(
        project__subsystem=subsystem,
        status=InvestRoadmapItem.Status.OPEN,
        due_at__lt=now,
    )


def mark_overdue() -> int:
    now = timezone.now()
    return InvestRoadmapItem.objects.filter(
        status=InvestRoadmapItem.Status.OPEN,
        due_at__lt=now,
    ).update(status=InvestRoadmapItem.Status.OVERDUE)
