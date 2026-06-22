"""Уведомления администраторам о принудительном импорте/откате Студии."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from delayu.models import Notification, NotificationTemplate, SubsystemMembership
from delayu.services.notify_dispatch import dispatch_event

User = get_user_model()

FORCED_IMPORT_EVENT = "studio.forced_import"


def _subsystem_admins(subsystem):
    return User.objects.filter(
        subsystem_memberships__subsystem=subsystem,
        subsystem_memberships__role__code="admin",
        is_active=True,
    ).distinct()


def notify_studio_forced_import(subsystem, actor, risk: dict, *, action: str = "import") -> int:
    """In-app/e-mail администраторам подсистемы при force=true."""
    admins = list(_subsystem_admins(subsystem))
    if not admins:
        return 0
    critical = risk.get("critical") or []
    summary = "; ".join(r.get("message", "") for r in critical[:5]) or "Критические изменения"
    actor_name = actor.get_full_name() or actor.username if actor else "—"
    ctx = {
        "subsystem": subsystem.name,
        "user": actor_name,
        "comment": summary,
        "critical": summary,
        "link": "/studio/",
        "action": "импорт" if action == "import" else "откат",
    }
    has_templates = NotificationTemplate.objects.filter(
        subsystem=subsystem,
        event_code=FORCED_IMPORT_EVENT,
        is_active=True,
    ).exists()
    if has_templates:
        dispatch_event(subsystem, FORCED_IMPORT_EVENT, admins, ctx)
        return len(admins)
    title = f"Студия: принудительный {ctx['action']}"
    body = f"{actor_name}: {summary}"
    for admin in admins:
        if admin.pk == getattr(actor, "pk", None):
            continue
        Notification.objects.create(
            user=admin,
            subsystem=subsystem,
            title=title[:255],
            body=body[:2000],
            link="/studio/",
            level=Notification.Level.WARNING,
        )
    return len(admins)
