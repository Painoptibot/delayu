"""#50 — интерактивный онбординг."""
from __future__ import annotations

from django.utils import timezone

from delayu.models import UserProfile


def profile_state(user) -> dict:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    state = dict(profile.onboarding_state or {})
    state.setdefault("completed", [])
    state.setdefault("current_step", 0)
    return state


def save_state(user, state: dict) -> None:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.onboarding_state = state
    profile.save(update_fields=["onboarding_state", "updated_at"])


def mark_step(user, step_id: str) -> dict:
    state = profile_state(user)
    completed = list(state.get("completed") or [])
    if step_id not in completed:
        completed.append(step_id)
    state["completed"] = completed
    save_state(user, state)
    return state


def dismiss_onboarding(user) -> None:
    state = profile_state(user)
    state["dismissed_at"] = timezone.now().isoformat()
    save_state(user, state)


def is_dismissed(user) -> bool:
    return bool(profile_state(user).get("dismissed_at"))


def build_steps(user, membership) -> list[dict]:
    from delayu.models import CaseFile, Correspondence, TaskItem
    from django.urls import reverse

    profile = UserProfile.objects.filter(user=user).first()
    state = profile_state(user)
    manual = set(state.get("completed") or [])

    raw = [
        {
            "id": "profile",
            "title": "Заполнить профиль",
            "hint": "Укажите телефон в личном кабинете.",
            "done": bool(profile and profile.phone) or "profile" in manual,
            "url": reverse("platform-cabinet"),
        },
        {
            "id": "subsystem",
            "title": "Подсистема активна",
            "hint": "Вы работаете в выбранном контуре.",
            "done": membership is not None or "subsystem" in manual,
            "url": reverse("platform-home"),
        },
        {
            "id": "case",
            "title": "Открыть реестр дел",
            "hint": "Создайте или найдите дело.",
            "done": (
                membership
                and CaseFile.objects.filter(subsystem=membership.subsystem).exists()
            )
            or "case" in manual,
            "url": reverse("platform-cases"),
        },
        {
            "id": "inbound",
            "title": "Входящая корреспонденция",
            "hint": "Зарегистрируйте входящий документ.",
            "done": (
                membership
                and Correspondence.objects.filter(
                    subsystem=membership.subsystem, direction=Correspondence.Direction.IN
                ).exists()
            )
            or "inbound" in manual,
            "url": reverse("platform-correspondence-inbound"),
        },
        {
            "id": "task",
            "title": "Задача в workplace",
            "hint": "Поставьте себе задачу.",
            "done": (
                membership
                and TaskItem.objects.filter(subsystem=membership.subsystem, assignee=user).exists()
            )
            or "task" in manual,
            "url": reverse("platform-task-create"),
        },
        {
            "id": "search",
            "title": "Глобальный поиск",
            "hint": "Нажмите Ctrl+K и найдите объект.",
            "done": "search" in manual,
            "url": reverse("platform-cases"),
        },
    ]
    for i, step in enumerate(raw):
        step["index"] = i + 1
    return raw
