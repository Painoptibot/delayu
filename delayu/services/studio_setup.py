"""Мастер первичной настройки подсистемы в Студии."""
from __future__ import annotations

from django.urls import reverse

from delayu.models import (
    IntegrationEndpoint,
    Role,
    StudioConfigRevision,
    SubsystemMembership,
)

SETUP_STEPS = [
    {
        "id": "blueprint",
        "title": "Шаблон конфигурации",
        "hint": "Примените готовый шаблон меню и маршрута СЭД.",
        "action": "blueprint",
    },
    {
        "id": "roles",
        "title": "Роли подсистемы",
        "hint": "Создайте хотя бы одну роль (оператор, руководитель).",
        "url_name": "platform-roles",
    },
    {
        "id": "users",
        "title": "Пользователи",
        "hint": "Назначьте пользователей в подсистему.",
        "url_name": "platform-users",
    },
    {
        "id": "publish",
        "title": "Публикация конфигурации",
        "hint": "Опубликуйте черновик — создастся первая ревизия.",
        "action": "publish",
    },
    {
        "id": "integrations",
        "title": "Точка СМЭВ",
        "hint": "Создайте stub-endpoint СМЭВ для pipeline.",
        "action": "smev_stub",
    },
]


def _completed_ids(subsystem) -> set[str]:
    state = subsystem.studio_setup_state or {}
    return set(state.get("completed") or [])


def _auto_done(subsystem, step_id: str) -> bool:
    if step_id == "blueprint":
        return bool(
            subsystem.studio_has_draft
            or subsystem.menu_layout
            or subsystem.correspondence_workflow
        )
    if step_id == "roles":
        return Role.objects.filter(subsystem=subsystem).exists()
    if step_id == "users":
        return SubsystemMembership.objects.filter(subsystem=subsystem).exists()
    if step_id == "publish":
        return bool(
            subsystem.published_at
            or StudioConfigRevision.objects.filter(subsystem=subsystem).exists()
        )
    if step_id == "integrations":
        return IntegrationEndpoint.objects.filter(
            subsystem=subsystem, endpoint_type=IntegrationEndpoint.EndpointType.SMEV
        ).exists()
    return False


def build_setup_steps(subsystem) -> list[dict]:
    manual = _completed_ids(subsystem)
    steps = []
    for idx, step in enumerate(SETUP_STEPS, start=1):
        done = _auto_done(subsystem, step["id"]) or step["id"] in manual
        item = dict(step)
        item["index"] = idx
        item["done"] = done
        if step.get("url_name"):
            item["url"] = reverse(step["url_name"])
        steps.append(item)
    return steps


def setup_progress(subsystem) -> dict:
    steps = build_setup_steps(subsystem)
    done = sum(1 for s in steps if s["done"])
    total = len(steps)
    state = subsystem.studio_setup_state or {}
    return {
        "steps": steps,
        "done": done,
        "total": total,
        "percent": int(100 * done / total) if total else 0,
        "complete": done == total if total else False,
        "dismissed": bool(state.get("dismissed_at")),
    }


def mark_setup_step(subsystem, step_id: str) -> dict:
    state = dict(subsystem.studio_setup_state or {})
    completed = list(state.get("completed") or [])
    if step_id not in completed:
        completed.append(step_id)
    state["completed"] = completed
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return setup_progress(subsystem)


def dismiss_setup_wizard(subsystem) -> None:
    state = dict(subsystem.studio_setup_state or {})
    from django.utils import timezone

    state["dismissed_at"] = timezone.now().isoformat()
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])


def init_setup_for_new_subsystem(subsystem) -> None:
    """Пометить подсистему для автозапуска мастера настройки."""
    if subsystem.studio_setup_state:
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        ensure_studio_notification_templates(subsystem)
        return
    subsystem.studio_setup_state = {"auto_launch": True, "completed": []}
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    from delayu.services.studio_notification_templates import ensure_studio_notification_templates

    ensure_studio_notification_templates(subsystem)


def should_auto_launch_setup(subsystem) -> bool:
    """Перенаправить на /studio/setup/ при первом входе в Студию."""
    state = subsystem.studio_setup_state or {}
    if state.get("dismissed_at"):
        return False
    progress = setup_progress(subsystem)
    if progress["complete"]:
        return False
    if not state.get("auto_launch"):
        return False
    return not StudioConfigRevision.objects.filter(subsystem=subsystem).exists()


def ensure_smev_stub_endpoint(subsystem) -> IntegrationEndpoint:
    ep, created = IntegrationEndpoint.objects.get_or_create(
        subsystem=subsystem,
        code="smev_stub",
        defaults={
            "name": "СМЭВ 3.x (stub)",
            "endpoint_type": IntegrationEndpoint.EndpointType.SMEV,
            "description": "Создано мастером настройки Студии",
            "config": {
                "transport": "simulated",
                "test_mode": True,
                "message_type": "Request",
                "pipeline": {
                    "nodes": [
                        {"id": "src", "type": "source", "label": "Источник"},
                        {"id": "smev", "type": "smev", "label": "СМЭВ", "message_type": "Request"},
                    ],
                    "edges": [],
                },
            },
        },
    )
    return ep
