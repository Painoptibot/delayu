"""In-app уведомления по просроченным срокам АИС УЖВ."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from delayu.models import Notification
from delayu.models_uzhv import (
    HousingAppeal,
    HousingInteragencyRequest,
    HousingPrescription,
)

User = get_user_model()
DEDUP_HOURS = 20
SYNC_SESSION_MINUTES = 30


def _already_sent(user, subsystem, link: str) -> bool:
    cutoff = timezone.now() - timedelta(hours=DEDUP_HOURS)
    return Notification.objects.filter(
        user=user,
        subsystem=subsystem,
        link=link,
        is_read=False,
        created_at__gte=cutoff,
    ).exists()


def should_sync_uzhv_notifications(request, subsystem) -> bool:
    """Не чаще раза в SYNC_SESSION_MINUTES на сессию и подсистему."""
    import time

    key = f"uzhv_notify_sync_{subsystem.pk}"
    last = request.session.get(key)
    if last is not None and time.time() - float(last) < SYNC_SESSION_MINUTES * 60:
        return False
    return True


def mark_uzhv_notifications_synced(request, subsystem) -> None:
    import time

    request.session[f"uzhv_notify_sync_{subsystem.pk}"] = time.time()
    request.session.modified = True


def _notify(user, subsystem, *, title: str, body: str, link: str, level: str):
    """Оставлено для тестов; в sync используется локальная notify()."""
    if not user or not user.is_active:
        return
    if _already_sent(user, subsystem, link):
        return
    Notification.objects.create(
        user=user,
        subsystem=subsystem,
        title=title[:255],
        body=body[:2000],
        link=link[:500],
        level=level,
    )


def sync_uzhv_deadline_notifications(subsystem) -> dict:
    """Создаёт in-app уведомления исполнителям по просроченным срокам."""
    today = timezone.now().date()
    created = 0
    push_sent = 0

    def notify(user, *, title: str, body: str, link: str, level: str):
        nonlocal created, push_sent
        if not user or not user.is_active:
            return
        if _already_sent(user, subsystem, link):
            return
        Notification.objects.create(
            user=user,
            subsystem=subsystem,
            title=title[:255],
            body=body[:2000],
            link=link[:500],
            level=level,
        )
        created += 1
        if level == Notification.Level.URGENT:
            from delayu.services.notify_dispatch import notify_uzhv_deadline_urgent

            if notify_uzhv_deadline_urgent(
                subsystem,
                user,
                title=title,
                body=body,
                link=link,
            ):
                push_sent += 1

    appeals = HousingAppeal.objects.filter(subsystem=subsystem).exclude(
        status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
    ).filter(due_date__lt=today).select_related("assignee")
    for a in appeals:
        if not a.assignee_id:
            continue
        link = reverse("uzhv-appeals") + f"?open={a.pk}"
        notify(
            a.assignee,
            title=f"УЖВ: просрочено обращение {a.appeal_number}",
            body=f"Срок ответа {a.due_date:%d.%m.%Y}. {a.subject[:120]}",
            link=link,
            level=Notification.Level.URGENT,
        )

    prescriptions = (
        HousingPrescription.objects.filter(inspection__subsystem=subsystem)
        .exclude(
            status__in=[
                HousingPrescription.Status.FULFILLED,
                HousingPrescription.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today)
        .select_related("inspection", "inspection__inspector")
    )
    for p in prescriptions:
        user = p.inspection.inspector if p.inspection_id else None
        if not user:
            continue
        link = reverse("uzhv-prescriptions") + f"?open={p.pk}"
        notify(
            user,
            title=f"УЖВ: просрочено предписание {p.prescription_number}",
            body=f"Срок устранения {p.due_date:%d.%m.%Y}. {p.description[:120]}",
            link=link,
            level=Notification.Level.WARNING,
        )

    interagency = (
        HousingInteragencyRequest.objects.filter(subsystem=subsystem)
        .exclude(
            status__in=[
                HousingInteragencyRequest.Status.ANSWERED,
                HousingInteragencyRequest.Status.CANCELLED,
            ]
        )
        .filter(due_date__lt=today)
        .select_related("housing_case", "housing_case__assignee", "created_by")
    )
    for r in interagency:
        user = None
        if r.housing_case_id and r.housing_case.assignee_id:
            user = r.housing_case.assignee
        elif r.created_by_id:
            user = r.created_by
        if not user:
            continue
        link = reverse("uzhv-interagency") + f"?open={r.pk}"
        notify(
            user,
            title=f"УЖВ: просрочен межвед. запрос {r.request_number}",
            body=f"Срок ответа {r.due_date:%d.%m.%Y}. {r.recipient_name[:80]}",
            link=link,
            level=Notification.Level.WARNING,
        )

    due_soon = HousingAppeal.objects.filter(subsystem=subsystem).exclude(
        status__in=[HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED]
    ).filter(
        due_date__gte=today,
        due_date__lte=today + timedelta(days=2),
    ).select_related("assignee")
    for a in due_soon:
        if not a.assignee_id:
            continue
        link = reverse("uzhv-appeals") + f"?open={a.pk}"
        notify(
            a.assignee,
            title=f"УЖВ: срок обращения {a.appeal_number} через {(a.due_date - today).days} дн.",
            body=f"Ответ до {a.due_date:%d.%m.%Y}. {a.subject[:120]}",
            link=link,
            level=Notification.Level.INFO,
        )

    return {"created": created, "push_sent": push_sent}
