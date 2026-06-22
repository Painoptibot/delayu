"""Исходящие события публикации конфигурации Студии (webhook)."""
from __future__ import annotations

from django.contrib.auth import get_user_model

from delayu.services.integration_events import emit_integration_event

User = get_user_model()

STUDIO_PUBLISH_EVENT = "studio.config_published"
STUDIO_RESTORE_EVENT = "studio.config_restored"
STUDIO_REVISIONS_PRUNED_EVENT = "studio.revisions_pruned"
STUDIO_ACTIVITY_DIGEST_EVENT = "studio.activity_digest"
STUDIO_COMPLIANCE_EXPORT_EVENT = "studio.compliance_export"
STUDIO_REVISION_META_EVENT = "studio.revision_meta"
STUDIO_REVISION_TAGS_BULK_EVENT = "studio.revision_tags_bulk"


def emit_studio_config_published(
    subsystem,
    revision,
    user,
    *,
    comment: str = "",
    source: str = "studio",
) -> int:
    """
    Webhook studio.config_published на активные коннекторы webhook/rest
    с events, содержащим studio.config_published или *.
    """
    version = revision.version_label if revision else subsystem.config_version
    publisher = ""
    if user:
        publisher = user.get_full_name() or user.username
    data = {
        "id": revision.pk if revision else "",
        "external_id": f"studio-publish:{subsystem.code}:{version}",
        "version": version,
        "revision_id": revision.pk if revision else None,
        "comment": (comment or "").strip(),
        "published_by": publisher,
        "published_by_id": user.pk if user else None,
        "source": source,
        "has_draft_remaining": bool(subsystem.studio_has_draft),
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_PUBLISH_EVENT, data)


def emit_studio_config_restored(
    subsystem,
    source_revision,
    user,
    *,
    mode: str = "draft",
    from_version: str = "",
    forced: bool = False,
    new_revision=None,
) -> int:
    """Webhook studio.config_restored после отката к ревизии."""
    actor = user.get_full_name() or user.username if user else ""
    version = (
        new_revision.version_label
        if new_revision
        else (source_revision.version_label if source_revision else subsystem.config_version)
    )
    data = {
        "id": source_revision.pk if source_revision else "",
        "external_id": f"studio-restore:{subsystem.code}:{from_version or version}",
        "from_version": from_version or (source_revision.version_label if source_revision else ""),
        "version": version,
        "revision_id": source_revision.pk if source_revision else None,
        "new_revision_id": new_revision.pk if new_revision else None,
        "mode": mode,
        "forced": forced,
        "restored_by": actor,
        "restored_by_id": user.pk if user else None,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_RESTORE_EVENT, data)


def emit_studio_revisions_pruned(subsystem, user, *, keep: int, deleted: int, remaining: int) -> int:
    """Webhook studio.revisions_pruned после очистки старых ревизий."""
    actor = user.get_full_name() or user.username if user else ""
    data = {
        "external_id": f"studio-prune:{subsystem.code}:{keep}:{deleted}",
        "keep": keep,
        "deleted": deleted,
        "remaining": remaining,
        "pruned_by": actor,
        "pruned_by_id": user.pk if user else None,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_REVISIONS_PRUNED_EVENT, data)


def on_studio_revisions_pruned(
    subsystem,
    user,
    *,
    keep: int,
    deleted: int,
    remaining: int,
) -> int:
    """Webhook после очистки ревизий."""
    if deleted <= 0:
        return 0
    return emit_studio_revisions_pruned(
        subsystem, user, keep=keep, deleted=deleted, remaining=remaining
    )


def emit_studio_compliance_export(
    subsystem,
    user,
    *,
    filename: str,
    size: int,
    source: str = "manual",
    mask_pii: bool = False,
    revision_tag: str = "",
) -> int:
    """Webhook studio.compliance_export после экспорта compliance ZIP."""
    actor = user.get_full_name() or user.username if user else ""
    data = {
        "external_id": f"studio-compliance:{subsystem.code}:{filename}",
        "filename": filename,
        "size": size,
        "source": source,
        "mask_pii": mask_pii,
        "revision_tag": (revision_tag or "").strip() or None,
        "exported_by": actor,
        "exported_by_id": user.pk if user else None,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_COMPLIANCE_EXPORT_EVENT, data)


def on_studio_compliance_exported(
    subsystem,
    user,
    *,
    filename: str,
    size: int,
    source: str = "manual",
    mask_pii: bool = False,
    revision_tag: str = "",
) -> int:
    """Webhook после экспорта compliance-пакета."""
    return emit_studio_compliance_export(
        subsystem,
        user,
        filename=filename,
        size=size,
        source=source,
        mask_pii=mask_pii,
        revision_tag=revision_tag,
    )


def emit_studio_revision_meta_updated(
    subsystem,
    user,
    revision,
    *,
    comment: str = "",
    tags: list | None = None,
) -> int:
    """Webhook studio.revision_meta после изменения метаданных ревизии."""
    actor = user.get_full_name() or user.username if user else ""
    data = {
        "external_id": f"studio-revision-meta:{subsystem.code}:{revision.pk}",
        "revision_id": revision.pk,
        "version": revision.version_label,
        "comment": comment or "",
        "tags": tags or [],
        "updated_by": actor,
        "updated_by_id": user.pk if user else None,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_REVISION_META_EVENT, data)


def on_studio_revision_meta_updated(
    subsystem,
    user,
    revision,
    *,
    comment: str = "",
    tags: list | None = None,
) -> int:
    return emit_studio_revision_meta_updated(
        subsystem, user, revision, comment=comment, tags=tags
    )


def emit_studio_revision_tags_bulk(
    subsystem,
    user,
    *,
    revision_ids: list,
    mode: str,
    tags: list,
    count: int,
) -> int:
    """Webhook studio.revision_tags_bulk после массового изменения тегов."""
    actor = user.get_full_name() or user.username if user else ""
    data = {
        "external_id": f"studio-revision-tags-bulk:{subsystem.code}:{count}",
        "revision_ids": revision_ids,
        "mode": mode,
        "tags": tags or [],
        "count": count,
        "updated_by": actor,
        "updated_by_id": user.pk if user else None,
        "subsystem_name": subsystem.name,
    }
    return emit_integration_event(subsystem, STUDIO_REVISION_TAGS_BULK_EVENT, data)


def on_studio_revision_tags_bulk(
    subsystem,
    user,
    *,
    revision_ids: list,
    mode: str,
    tags: list,
    count: int,
) -> int:
    return emit_studio_revision_tags_bulk(
        subsystem,
        user,
        revision_ids=revision_ids,
        mode=mode,
        tags=tags,
        count=count,
    )


def on_studio_config_restored(
    subsystem,
    source_revision,
    user,
    *,
    mode: str = "draft",
    from_version: str = "",
    forced: bool = False,
    new_revision=None,
    restore_risk: dict | None = None,
) -> int:
    """Webhook + уведомления при откате конфигурации."""
    count = emit_studio_config_restored(
        subsystem,
        source_revision,
        user,
        mode=mode,
        from_version=from_version,
        forced=forced,
        new_revision=new_revision,
    )
    notify_studio_config_restored(
        subsystem,
        source_revision,
        user,
        mode=mode,
        from_version=from_version,
        forced=forced,
        new_revision=new_revision,
    )
    if forced and restore_risk and restore_risk.get("blocked"):
        from delayu.services.studio_forced_import import notify_studio_forced_import

        notify_studio_forced_import(subsystem, user, restore_risk, action="restore")
    return count


def notify_studio_config_restored(
    subsystem,
    source_revision,
    user,
    *,
    mode: str = "draft",
    from_version: str = "",
    forced: bool = False,
    new_revision=None,
    link: str = "/studio/",
) -> None:
    """In-app и e-mail по шаблонам M78 studio.config_restored."""
    if not user:
        return
    from delayu.models import NotificationTemplate
    from delayu.services.notify_dispatch import dispatch_event

    version = from_version or (
        source_revision.version_label if source_revision else subsystem.config_version
    )
    ctx = {
        "from_version": version,
        "mode": mode,
        "forced": "да" if forced else "нет",
        "link": link,
        "subsystem": subsystem.name,
        "user": user.get_full_name() or user.username,
        "new_version": new_revision.version_label if new_revision else "",
    }
    if NotificationTemplate.objects.filter(
        subsystem=subsystem,
        event_code=STUDIO_RESTORE_EVENT,
        is_active=True,
    ).exists():
        dispatch_event(subsystem, STUDIO_RESTORE_EVENT, [user], ctx)


def notify_studio_config_published(
    subsystem,
    revision,
    user,
    *,
    comment: str = "",
    link: str = "/studio/",
) -> None:
    """In-app и e-mail по шаблонам M78 studio.config_published."""
    if not user:
        return
    from delayu.models import NotificationTemplate
    from delayu.services.notify_dispatch import dispatch_event

    version = revision.version_label if revision else subsystem.config_version
    body = (comment or "").strip() or "Конфигурация опубликована."
    ctx = {
        "version": version,
        "comment": body,
        "link": link,
        "subsystem": subsystem.name,
        "user": user.get_full_name() or user.username,
    }
    if NotificationTemplate.objects.filter(
        subsystem=subsystem,
        event_code=STUDIO_PUBLISH_EVENT,
        is_active=True,
    ).exists():
        dispatch_event(subsystem, STUDIO_PUBLISH_EVENT, [user], ctx)


def on_studio_config_published(
    subsystem,
    revision,
    user,
    *,
    comment: str = "",
    source: str = "studio",
) -> int:
    """Webhook + уведомления при публикации конфигурации."""
    count = emit_studio_config_published(
        subsystem, revision, user, comment=comment, source=source
    )
    notify_studio_config_published(subsystem, revision, user, comment=comment)
    return count
