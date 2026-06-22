"""Шаблоны уведомлений M78 для событий Студии."""
from __future__ import annotations

from delayu.models import NotificationTemplate

_STUDIO_TEMPLATES = (
    (
        "studio_scheduled_publish",
        NotificationTemplate.Channel.IN_APP,
        "Студия: опубликована {version}",
        "Конфигурация {version} опубликована по расписанию. {comment}\n{link}",
    ),
    (
        "studio_scheduled_publish",
        NotificationTemplate.Channel.EMAIL,
        "Студия: опубликована {version}",
        "Подсистема: {subsystem}\nВерсия: {version}\n{comment}\n\nОткрыть Студию: {link}",
    ),
    (
        "studio_scheduled_publish",
        NotificationTemplate.Channel.SMS,
        "Студия {version}",
        "Опубликована конфигурация {version}. {comment} {link}",
    ),
    (
        "studio.config_published",
        NotificationTemplate.Channel.IN_APP,
        "Студия: опубликована {version}",
        "Конфигурация {version} опубликована. {comment}\n{link}",
    ),
    (
        "studio.config_published",
        NotificationTemplate.Channel.EMAIL,
        "Студия: опубликована {version}",
        "Подсистема: {subsystem}\nВерсия: {version}\nОпубликовал: {user}\n{comment}\n\n{link}",
    ),
    (
        "studio.forced_import",
        NotificationTemplate.Channel.IN_APP,
        "Студия: принудительный {action}",
        "{user} выполнил принудительный {action}.\n{critical}\n{link}",
    ),
    (
        "studio.forced_import",
        NotificationTemplate.Channel.EMAIL,
        "Студия: принудительный {action}",
        "Подсистема: {subsystem}\nПользователь: {user}\nДействие: принудительный {action}\n{critical}\n\n{link}",
    ),
    (
        "studio.config_restored",
        NotificationTemplate.Channel.IN_APP,
        "Студия: откат к {from_version}",
        "Конфигурация откачена к {from_version} ({mode}). {user}\n{link}",
    ),
    (
        "studio.config_restored",
        NotificationTemplate.Channel.EMAIL,
        "Студия: откат к {from_version}",
        "Подсистема: {subsystem}\nОткат к: {from_version}\nРежим: {mode}\nПользователь: {user}\n{link}",
    ),
    (
        "studio.config_restored",
        NotificationTemplate.Channel.SMS,
        "Студия: откат {from_version}",
        "Откат к {from_version} ({mode}). {user} {link}",
    ),
    (
        "studio.activity_digest",
        NotificationTemplate.Channel.IN_APP,
        "Студия: сводка за {days} дн.",
        "Событий: {total}, forced: {forced_count}\n{summary}\n{link}",
    ),
    (
        "studio.activity_digest",
        NotificationTemplate.Channel.EMAIL,
        "Студия: сводка активности ({days} дн.)",
        "Подсистема: {subsystem}\nПериод: {days} дн.\nСобытий: {total}\nПринудительных: {forced_count}\n\n{summary}\n\n{link}",
    ),
)


def ensure_studio_notification_templates(subsystem) -> int:
    """Создать шаблоны событий Студии (scheduled, publish, restore, forced, digest)."""
    created = 0
    for event_code, channel, subject, body in _STUDIO_TEMPLATES:
        _, was_created = NotificationTemplate.objects.get_or_create(
            subsystem=subsystem,
            event_code=event_code,
            channel=channel,
            defaults={"subject": subject, "body": body, "is_active": True},
        )
        if was_created:
            created += 1
    return created
