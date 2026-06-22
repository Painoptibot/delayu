"""Счётчики для бейджей пунктов меню (#22)."""
from django.utils import timezone

from delayu.models import BPMTask, Notification, TaskItem
from delayu.models_business import Correspondence


MENU_BADGE_OPTIONS = [
    ("", "Без счётчика"),
    ("inbox", "Входящие (непрочит.)"),
    ("approvals", "Согласования"),
    ("overdue", "Просрочки"),
    ("notifications", "Уведомления"),
    ("tasks", "Открытые задачи"),
]


def menu_badge_counts(user, subsystem) -> dict[str, int]:
    if not user or not user.is_authenticated:
        return {}
    today = timezone.now().date()
    return {
        "inbox": Correspondence.objects.filter(
            subsystem=subsystem,
            direction=Correspondence.Direction.IN,
            is_read=False,
            is_deleted=False,
            is_draft=False,
        ).count(),
        "approvals": BPMTask.objects.filter(
            assignee=user,
            status=BPMTask.Status.PENDING,
            instance__template__subsystem=subsystem,
        ).count(),
        "overdue": TaskItem.objects.filter(
            subsystem=subsystem,
            assignee=user,
            completed_at__isnull=True,
            due_date__lt=today,
        ).count(),
        "notifications": Notification.objects.filter(
            user=user,
            subsystem=subsystem,
            is_read=False,
        ).count(),
        "tasks": TaskItem.objects.filter(
            subsystem=subsystem,
            assignee=user,
            completed_at__isnull=True,
        ).count(),
    }


def badge_tuple(key: str, count: int) -> list | None:
    if not key or count <= 0:
        return None
    color = "danger" if key == "overdue" else "primary"
    if key == "approvals":
        color = "warning"
    return [color, count]


def apply_menu_badges(menu: list, user, subsystem) -> list:
    counts = menu_badge_counts(user, subsystem)
    out = []
    for entry in menu:
        if "menu_header" in entry:
            out.append(entry)
            continue
        row = dict(entry)
        key = entry.get("badge_key")
        if key:
            bt = badge_tuple(key, counts.get(key, 0))
            if bt:
                row["badge"] = bt
        out.append(row)
    return out


def inject_pinned_section(menu: list, pinned: list[dict]) -> list:
    if not pinned:
        return menu
    seen = {e.get("url") for e in menu if e.get("url")}
    items = [p for p in pinned if p.get("url") not in seen]
    if not items:
        return menu
    return [{"menu_header": "Быстрый доступ"}] + items + menu
