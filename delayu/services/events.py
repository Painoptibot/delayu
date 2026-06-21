"""Единый журнал доменных событий (Event Sourcing lite)."""
from delayu.models import ActivityEvent, AuditLog, CorrespondenceEvent
from delayu.services import audit


def record_event(
    *,
    subsystem,
    actor,
    action: str,
    model_name: str = "",
    object_id="",
    payload=None,
    request=None,
    description: str = "",
):
    """AuditLog + ActivityEvent для ключевых изменений."""
    audit.log_action(
        actor,
        subsystem,
        action,
        model_name=model_name,
        object_id=object_id,
        payload=payload or {},
        request=request,
    )
    if description:
        ActivityEvent.objects.create(
            subsystem=subsystem,
            actor=actor,
            verb=action[:64],
            target_repr=description[:255],
            module_code=(payload or {}).get("module_code", ""),
        )


def record_correspondence_event(correspondence, event_type, description, *, actor=None, document=None):
    return CorrespondenceEvent.objects.create(
        correspondence=correspondence,
        document=document,
        event_type=event_type,
        description=description[:500],
        actor=actor,
    )
