"""Администрирование Студии: черновики, публикация, health-check."""
from __future__ import annotations

from django.utils import timezone

from delayu.models import (
    BPMTemplate,
    FormSchema,
    IntegrationEndpoint,
    NSIClassifier,
    NSIValue,
    PrintTemplate,
    Role,
    RoleStudioLayout,
    StudioConfigRevision,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.services import audit, studio


def draft_value(subsystem, key: str, *, live_fallback=True):
    """Значение из черновика или опубликованной конфигурации."""
    draft = subsystem.studio_draft or {}
    if key in draft:
        return draft[key]
    if not live_fallback:
        return None
    if key == "menu":
        return subsystem.menu_layout or studio.default_menu_layout()
    if key == "correspondence":
        return subsystem.correspondence_workflow or studio.default_correspondence_workflow()
    return None


def save_draft(subsystem, key: str, value) -> None:
    if key == "menu":
        value = studio.normalize_menu_layout(value)
    draft = dict(subsystem.studio_draft or {})
    draft[key] = value
    subsystem.studio_draft = draft
    subsystem.studio_has_draft = True
    subsystem.save(update_fields=["studio_draft", "studio_has_draft", "updated_at"])


def capture_snapshot(subsystem) -> dict:
    """Полный снимок конфигурации подсистемы для ревизии."""
    from delayu.services.retention import get_or_create_retention_policy
    from delayu.services.siem_export import get_or_create_siem_config

    retention = get_or_create_retention_policy(subsystem)
    siem = get_or_create_siem_config(subsystem)
    return {
        "menu_layout": subsystem.menu_layout or [],
        "correspondence_workflow": subsystem.correspondence_workflow or {},
        "forms": list(
            FormSchema.objects.filter(subsystem=subsystem).values(
                "id", "code", "target", "schema", "name"
            )
        ),
        "bpm": list(
            BPMTemplate.objects.filter(subsystem=subsystem).values(
                "id", "code", "name", "diagram", "steps"
            )
        ),
        "print": list(
            PrintTemplate.objects.filter(subsystem=subsystem).values("id", "code", "name", "body")
        ),
        "nsi": [
            {
                "id": clf.id,
                "code": clf.code,
                "name": clf.name,
                "description": clf.description,
                "is_active": clf.is_active,
                "values": [
                    {
                        "code": v.code,
                        "name": v.name,
                        "sort_order": v.sort_order,
                    }
                    for v in clf.values.filter(is_active=True).order_by("sort_order", "name")
                ],
            }
            for clf in NSIClassifier.objects.filter(subsystem=subsystem).order_by("code")
        ],
        "integrations": list(
            IntegrationEndpoint.objects.filter(subsystem=subsystem).values(
                "id",
                "code",
                "name",
                "description",
                "endpoint_type",
                "config",
                "is_active",
                "max_retries",
            )
        ),
        "role_layouts": [
            {
                "role_id": row.role_id,
                "role_code": row.role.code,
                "kind": row.kind,
                "widgets": row.widgets,
            }
            for row in RoleStudioLayout.objects.filter(subsystem=subsystem).select_related("role")
        ],
        "policies": {
            "retention_years": retention.default_archive_years,
            "alert_days": retention.alert_days_before,
            "auto_purge": retention.auto_purge_enabled,
            "siem_enabled": siem.enabled,
            "siem_webhook": bool(siem.webhook_url),
            "siem_webhook_url": siem.webhook_url or "",
        },
    }


def next_version_label(subsystem) -> str:
    last = subsystem.studio_revisions.order_by("-created_at").first()
    if last and last.version_label.startswith("v"):
        try:
            num = int(last.version_label[1:].split(".")[0])
            return f"v{num + 1}"
        except ValueError:
            pass
    base = (subsystem.config_version or "v1").strip()
    if base.startswith("v"):
        try:
            return f"v{int(base[1:]) + 1}"
        except ValueError:
            pass
    return "v2"


def publish_studio_draft(
    subsystem,
    user,
    comment: str = "",
    *,
    tags: list | None = None,
) -> StudioConfigRevision:
    """Применить черновик меню/СЭД и создать ревизию."""
    draft = dict(subsystem.studio_draft or {})
    if "menu" in draft:
        subsystem.menu_layout = draft.pop("menu") or []
    if "correspondence" in draft:
        subsystem.correspondence_workflow = draft.pop("correspondence") or {}

    subsystem.studio_draft = draft
    subsystem.studio_has_draft = bool(draft)
    version = next_version_label(subsystem)
    subsystem.config_version = version
    subsystem.published_at = timezone.now()
    subsystem.save(
        update_fields=[
            "menu_layout",
            "correspondence_workflow",
            "studio_draft",
            "studio_has_draft",
            "config_version",
            "published_at",
            "updated_at",
        ]
    )

    revision = StudioConfigRevision.objects.create(
        subsystem=subsystem,
        version_label=version,
        snapshot=capture_snapshot(subsystem),
        comment=(comment or "").strip()[:255],
        published_by=user,
    )
    from delayu.services.studio_publish_schedule import cancel_scheduled_publish

    cancel_scheduled_publish(subsystem)
    from delayu.services.studio_publish_events import on_studio_config_published

    on_studio_config_published(
        subsystem, revision, user, comment=comment, source="studio"
    )
    final_tags = merge_publish_tags(subsystem, tags)
    if final_tags:
        set_revision_tags(subsystem, revision.pk, final_tags)
    clear_pending_publish_tags(subsystem)
    return revision


def dry_run_publish(subsystem, *, tags: list | None = None) -> dict:
    """Сравнение опубликованного состояния с черновиком перед публикацией."""
    from delayu.services.config_diff import compare_policies
    from delayu.services.studio_revision_compare import compare_snapshots

    if not subsystem.studio_has_draft:
        return {"ok": False, "error": "no_draft"}
    draft_data = subsystem.studio_draft or {}
    draft_keys = [k for k in ("menu", "correspondence") if k in draft_data]
    if not draft_keys:
        return {"ok": False, "error": "empty_draft"}
    live = effective_snapshot(subsystem, include_draft=False)
    with_draft = effective_snapshot(subsystem, include_draft=True)
    diff = compare_snapshots(live, with_draft)
    latest = (
        StudioConfigRevision.objects.filter(subsystem=subsystem).order_by("-pk").first()
    )
    published_policies = baseline_policies(
        subsystem, revision_id=latest.pk if latest else None
    )
    current_policies = current_policies_snapshot(subsystem)
    policies_diff = compare_policies(published_policies, current_policies)
    tags_preview = preview_publish_tags(subsystem, tags)
    return {
        "ok": True,
        "dry_run": True,
        "diff": diff,
        "draft_sections": draft_keys,
        "next_version": next_version_label(subsystem),
        "has_changes": bool(diff.get("changed_sections")),
        "current_version": subsystem.config_version or "",
        "policies_diff": policies_diff,
        "policies_drift": bool(policies_diff.get("changed")),
        "baseline_revision": latest.version_label if latest else "",
        "publish_tags": tags_preview["merged"],
        "publish_tags_breakdown": {
            "explicit": tags_preview["explicit"],
            "pending": tags_preview["pending"],
            "default": tags_preview["default"],
        },
    }


def dry_run_restore(
    subsystem,
    revision: StudioConfigRevision,
    *,
    mode: str = "draft",
) -> dict:
    """Предпросмотр отката: текущее состояние vs снимок ревизии."""
    from delayu.services.config_diff import compare_policies
    from delayu.services.studio_revision_compare import compare_snapshots

    if mode not in ("draft", "apply"):
        raise ValueError("invalid mode")
    target = revision.snapshot or {}
    current = effective_snapshot(subsystem, include_draft=True)
    diff = compare_snapshots(current, target)
    policies_diff = compare_policies(
        current_policies_snapshot(subsystem),
        target.get("policies") or {},
    )
    from delayu.services.studio_import_risk import evaluate_restore_risk

    risk = evaluate_restore_risk(current, target)
    entity_diffs = compare_restore_entity_diffs(current, target)
    config_changed = bool(diff.get("changed_sections"))
    policies_changed = bool(policies_diff.get("changed"))
    return {
        "ok": True,
        "dry_run": True,
        "mode": mode,
        "from_version": revision.version_label,
        "revision_id": revision.pk,
        "diff": diff,
        "policies_diff": policies_diff,
        "risk": risk,
        "entity_diffs": entity_diffs,
        "has_changes": config_changed or policies_changed or entity_diffs["has_form_changes"] or entity_diffs["has_bpm_changes"],
        "config_changed": config_changed,
        "policies_changed": policies_changed,
    }


def compare_restore_entity_diffs(current: dict, target: dict) -> dict:
    """Diff форм и BPM при откате: текущее состояние → снимок ревизии."""
    from delayu.services.config_diff import compare_bpm_templates
    from delayu.services.form_schema_diff import compare_form_schemas

    cur_forms = {r["code"]: r for r in (current.get("forms") or []) if r.get("code")}
    tgt_forms = {r["code"]: r for r in (target.get("forms") or []) if r.get("code")}
    forms = []
    for code in sorted(set(cur_forms) | set(tgt_forms)):
        if code not in cur_forms:
            forms.append(
                {
                    "code": code,
                    "change": "added",
                    "name": tgt_forms[code].get("name") or code,
                }
            )
        elif code not in tgt_forms:
            forms.append(
                {
                    "code": code,
                    "change": "removed",
                    "name": cur_forms[code].get("name") or code,
                }
            )
        else:
            detail = compare_form_schemas(
                cur_forms[code].get("schema") or [],
                tgt_forms[code].get("schema") or [],
            )
            if detail["added"] or detail["removed"] or detail["changed"]:
                forms.append(
                    {
                        "code": code,
                        "change": "modified",
                        "name": cur_forms[code].get("name") or code,
                        "detail": detail,
                    }
                )

    cur_bpm = {r["code"]: r for r in (current.get("bpm") or []) if r.get("code")}
    tgt_bpm = {r["code"]: r for r in (target.get("bpm") or []) if r.get("code")}
    bpm = []
    for code in sorted(set(cur_bpm) | set(tgt_bpm)):
        if code not in cur_bpm:
            bpm.append(
                {
                    "code": code,
                    "change": "added",
                    "name": tgt_bpm[code].get("name") or code,
                }
            )
        elif code not in tgt_bpm:
            bpm.append(
                {
                    "code": code,
                    "change": "removed",
                    "name": cur_bpm[code].get("name") or code,
                }
            )
        else:
            detail = compare_bpm_templates(
                cur_bpm[code],
                tgt_bpm[code].get("diagram") or {},
            )
            if detail["added"] or detail["removed"] or detail["changed"] or detail["edges_changed"]:
                bpm.append(
                    {
                        "code": code,
                        "change": "modified",
                        "name": cur_bpm[code].get("name") or code,
                        "detail": detail,
                    }
                )

    return {
        "forms": forms,
        "bpm": bpm,
        "has_form_changes": bool(forms),
        "has_bpm_changes": bool(bpm),
    }


def discard_studio_draft(subsystem) -> None:
    from delayu.services.studio_publish_schedule import cancel_scheduled_publish

    subsystem.studio_draft = {}
    subsystem.studio_has_draft = False
    subsystem.save(update_fields=["studio_draft", "studio_has_draft", "updated_at"])
    cancel_scheduled_publish(subsystem)


def subsystem_health_checks(subsystem) -> list[dict]:
    """Чеклист готовности подсистемы для админ-обзора."""
    roles = Role.objects.filter(subsystem=subsystem).count()
    users = SubsystemMembership.objects.filter(subsystem=subsystem).count()
    modules = SubsystemModule.objects.filter(subsystem=subsystem, enabled=True).count()
    forms = FormSchema.objects.filter(subsystem=subsystem).count()
    bpm = BPMTemplate.objects.filter(subsystem=subsystem).count()
    nsi = NSIClassifier.objects.filter(subsystem=subsystem).count()
    integrations = IntegrationEndpoint.objects.filter(subsystem=subsystem).count()
    role_dashboards = RoleStudioLayout.objects.filter(
        subsystem=subsystem, kind=RoleStudioLayout.Kind.DASHBOARD
    ).count()

    checks = [
        {
            "id": "roles",
            "label": "Роли подсистемы",
            "status": "ok" if roles else "fail",
            "detail": f"{roles} ролей",
            "url_name": "platform-roles",
        },
        {
            "id": "users",
            "label": "Пользователи",
            "status": "ok" if users else "fail",
            "detail": f"{users} учётных записей",
            "url_name": "platform-users",
        },
        {
            "id": "modules",
            "label": "Включённые модули",
            "status": "ok" if modules >= 3 else "warn",
            "detail": f"{modules} модулей",
            "url_name": "platform-modules",
        },
        {
            "id": "forms",
            "label": "Схемы форм",
            "status": "ok" if forms else "warn",
            "detail": f"{forms} схем",
            "url_name": "platform-studio-forms",
        },
        {
            "id": "bpm",
            "label": "Шаблоны BPM",
            "status": "ok" if bpm else "warn",
            "detail": f"{bpm} процессов",
            "url_name": "platform-studio-bpm",
        },
        {
            "id": "nsi",
            "label": "Справочники НСИ",
            "status": "ok" if nsi else "warn",
            "detail": f"{nsi} классификаторов",
            "url_name": "platform-studio-nsi",
        },
        {
            "id": "integrations",
            "label": "Точки интеграции",
            "status": "ok" if integrations else "warn",
            "detail": f"{integrations} endpoint",
            "url_name": "platform-studio-integration",
        },
        {
            "id": "role_dashboards",
            "label": "Ролевые дашборды",
            "status": "ok" if role_dashboards else "warn",
            "detail": f"{role_dashboards} шаблонов",
            "url_name": "platform-studio-dashboard",
        },
        {
            "id": "menu",
            "label": "Меню подсистемы",
            "status": "ok" if subsystem.menu_layout else "warn",
            "detail": "настроено" if subsystem.menu_layout else "по умолчанию",
            "url_name": "platform-studio-menu",
        },
        {
            "id": "draft",
            "label": "Черновик Студии",
            "status": "warn" if subsystem.studio_has_draft else "ok",
            "detail": "есть неопубликованные изменения" if subsystem.studio_has_draft else "опубликовано",
            "url_name": "platform-studio",
        },
    ]
    return checks


def health_summary(checks: list[dict]) -> dict:
    return {
        "ok": sum(1 for c in checks if c["status"] == "ok"),
        "warn": sum(1 for c in checks if c["status"] == "warn"),
        "fail": sum(1 for c in checks if c["status"] == "fail"),
        "total": len(checks),
    }


def save_role_layout(subsystem, role, kind: str, widgets: list) -> RoleStudioLayout:
    obj, _ = RoleStudioLayout.objects.update_or_create(
        subsystem=subsystem,
        role=role,
        kind=kind,
        defaults={"widgets": widgets},
    )
    return obj


def role_layout_widgets(subsystem, role, kind: str) -> list | None:
    row = RoleStudioLayout.objects.filter(
        subsystem=subsystem, role=role, kind=kind
    ).first()
    if row and row.widgets:
        return row.widgets
    return None


def _preview_actor_user(subsystem):
    """Реальный User без superuser — только для is_superuser / filter_menu."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = (
        User.objects.filter(
            subsystem_memberships__subsystem=subsystem,
            is_superuser=False,
            is_active=True,
        )
        .order_by("pk")
        .first()
    )
    if user:
        return user
    user = User.objects.filter(is_superuser=False, is_active=True).order_by("pk").first()
    if user:
        return user
    user, _ = User.objects.get_or_create(
        username="__studio_preview__",
        defaults={
            "is_active": True,
            "is_superuser": False,
            "is_staff": False,
        },
    )
    return user


def _preview_membership(subsystem, role, *, organization=None):
    """Несохранённый membership: права роли + пользователь без superuser."""
    from delayu.models import Organization

    org = organization or Organization.objects.filter(
        subsystem=subsystem, is_active=True
    ).order_by("pk").first()
    return SubsystemMembership(
        user=_preview_actor_user(subsystem),
        subsystem=subsystem,
        role=role,
        organization=org,
    )


def preview_as_membership(subsystem, membership, *, include_draft: bool = False) -> dict:
    """Меню, модули и виджеты так, как увидит конкретный участник подсистемы."""
    from delayu.menu import build_menu_for_membership
    from delayu.services.role_inheritance import effective_matrix_row
    from delayu.services.roles import enabled_modules_for_subsystem

    role = membership.role
    orig_menu = subsystem.menu_layout
    try:
        if include_draft:
            draft_menu = (subsystem.studio_draft or {}).get("menu")
            if draft_menu is not None:
                subsystem.menu_layout = draft_menu
        menu = build_menu_for_membership(membership)
    finally:
        subsystem.menu_layout = orig_menu

    sections: list[dict] = []
    current = None
    for entry in menu:
        if entry.get("menu_header"):
            current = {"header": entry["menu_header"], "items": []}
            sections.append(current)
        elif entry.get("name") and current is not None:
            current["items"].append({"name": entry["name"], "icon": entry.get("icon", "")})

    modules = enabled_modules_for_subsystem(subsystem)
    perms = {
        p.module_id: p
        for p in role.module_permissions.select_related("module")
    }
    matrix = []
    denied = []
    for mod in modules:
        row = effective_matrix_row(role, mod, perms.get(mod.id))
        item = {
            "code": row["code"],
            "name": row["name"],
            "view": row["view"],
            "create": row["create"],
            "change": row["change"],
            "delete": row["delete"],
            "view_pii": row["view_pii"],
            "export_pii": row["export_pii"],
            "approve": row["approve"],
            "sign": row["sign"],
            "archive": row["archive"],
            "bulk": row["bulk"],
            "inherited": row.get("inherited", False),
        }
        matrix.append(item)
        if not row["view"]:
            denied.append({"code": mod.code, "name": mod.name})
    granted = [r for r in matrix if r.get("view")]

    dash = role_layout_widgets(subsystem, role, RoleStudioLayout.Kind.DASHBOARD) or []
    today = role_layout_widgets(subsystem, role, RoleStudioLayout.Kind.TODAY) or []

    corr = subsystem.correspondence_workflow or studio.default_correspondence_workflow()
    if include_draft:
        draft_corr = (subsystem.studio_draft or {}).get("correspondence")
        if draft_corr is not None:
            corr = draft_corr

    user = membership.user
    parent = role.parent_role
    return {
        "user": {
            "id": user.pk,
            "username": user.username,
            "name": user.get_full_name() or user.username,
        },
        "role": {
            "id": role.pk,
            "name": role.name,
            "code": role.code,
            "parent": parent.name if parent else "",
        },
        "organization": membership.organization.name if membership.organization_id else "",
        "include_draft": include_draft,
        "menu_sections": sections,
        "menu_item_count": sum(len(s["items"]) for s in sections),
        "modules_granted": len(granted),
        "modules_denied": len(denied),
        "permissions": granted[:24],
        "permission_matrix": matrix,
        "denied_modules": denied[:12],
        "dashboard_widgets": dash,
        "today_widgets": today,
        "correspondence_steps": (corr or {}).get("steps") or [],
    }


def preview_as_role(subsystem, role, *, include_draft: bool = False) -> dict:
    """Меню и права для роли (синтетический участник без superuser)."""
    membership = _preview_membership(subsystem, role)
    return preview_as_membership(subsystem, membership, include_draft=include_draft)


def effective_snapshot(subsystem, *, include_draft: bool = True) -> dict:
    """Текущий снимок с учётом черновика меню/СЭД."""
    snap = capture_snapshot(subsystem)
    if not include_draft:
        return snap
    draft = subsystem.studio_draft or {}
    if "menu" in draft:
        snap["menu_layout"] = draft["menu"]
    if "correspondence" in draft:
        snap["correspondence_workflow"] = draft["correspondence"]
    return snap


def export_config_package(subsystem) -> dict:
    """Полный пакет конфигурации для переноса между контурами."""
    snap = capture_snapshot(subsystem)
    role_codes = {
        r.pk: r.code for r in Role.objects.filter(subsystem=subsystem).only("pk", "code")
    }
    enriched_layouts = []
    for row in snap.get("role_layouts") or []:
        item = dict(row)
        item["role_code"] = role_codes.get(row.get("role_id"), "")
        enriched_layouts.append(item)
    snap["role_layouts"] = enriched_layouts

    return {
        "format": "delayu-studio-package",
        "format_version": 1,
        "exported_at": timezone.now().isoformat(),
        "subsystem": {"code": subsystem.code, "name": subsystem.name},
        "config_version": subsystem.config_version or "",
        "studio_has_draft": subsystem.studio_has_draft,
        "studio_draft": subsystem.studio_draft or {},
        "snapshot": snap,
    }


def import_config_package(
    subsystem, package: dict, *, to_draft: bool = True, force: bool = False
) -> dict:
    """Импорт пакета: меню/СЭД в черновик, ролевые шаблоны и схемы — по коду."""
    from delayu.services.studio_import_risk import ImportRiskError, evaluate_import_risk
    from delayu.services.studio_package_validate import validate_config_package

    validation = validate_config_package(package)
    if not validation["ok"]:
        raise ValueError("; ".join(validation["errors"]) or "Невалидный пакет")
    snap = package.get("snapshot") or package
    current = effective_snapshot(subsystem, include_draft=to_draft)
    risk = evaluate_import_risk(current, snap)
    if risk["blocked"] and not force:
        raise ImportRiskError(risk)
    stats = apply_snapshot(subsystem, snap, to_draft=to_draft)
    stats["validation_warnings"] = validation.get("warnings") or []
    stats["import_risk"] = risk
    return stats


def clone_studio_config(
    source,
    target,
    *,
    to_draft: bool = True,
    include_draft: bool = False,
) -> dict:
    """Клонировать конфигурацию Студии из одной подсистемы в другую."""
    if source.pk == target.pk:
        raise ValueError("Нельзя клонировать в ту же подсистему")
    package = export_config_package(source)
    if not include_draft:
        package["studio_draft"] = {}
        package["studio_has_draft"] = False
    stats = import_config_package(target, package, to_draft=to_draft)
    return {
        "ok": True,
        "source": source.code,
        "target": target.code,
        "to_draft": to_draft,
        "include_draft": include_draft,
        "stats": stats,
    }


def apply_snapshot(subsystem, snap: dict, *, to_draft: bool = True) -> dict:
    """Применить снимок конфигурации (импорт или откат)."""
    stats = {
        "menu": False,
        "correspondence": False,
        "role_layouts": 0,
        "forms": 0,
        "bpm": 0,
        "print": 0,
        "nsi": 0,
        "integrations": 0,
        "policies": False,
    }

    if to_draft:
        if snap.get("menu_layout") is not None:
            save_draft(subsystem, "menu", studio.normalize_menu_layout(snap["menu_layout"]))
            stats["menu"] = True
        if snap.get("correspondence_workflow") is not None:
            save_draft(subsystem, "correspondence", snap["correspondence_workflow"])
            stats["correspondence"] = True
    else:
        if snap.get("menu_layout") is not None:
            subsystem.menu_layout = studio.normalize_menu_layout(snap["menu_layout"])
            stats["menu"] = True
        if snap.get("correspondence_workflow") is not None:
            subsystem.correspondence_workflow = snap["correspondence_workflow"]
            stats["correspondence"] = True
        subsystem.save(
            update_fields=["menu_layout", "correspondence_workflow", "updated_at"]
        )

    role_by_code = {r.code: r for r in Role.objects.filter(subsystem=subsystem)}
    for row in snap.get("role_layouts") or []:
        code = row.get("role_code") or ""
        role = role_by_code.get(code)
        if not role:
            rid = row.get("role_id")
            role = Role.objects.filter(subsystem=subsystem, pk=rid).first()
        if not role:
            continue
        save_role_layout(subsystem, role, row.get("kind") or "", row.get("widgets") or [])
        stats["role_layouts"] += 1

    for form_row in snap.get("forms") or []:
        code = form_row.get("code")
        if not code:
            continue
        FormSchema.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "name": form_row.get("name") or code,
                "target": form_row.get("target") or "case",
                "schema": form_row.get("schema") or [],
            },
        )
        stats["forms"] += 1

    for bpm_row in snap.get("bpm") or []:
        code = bpm_row.get("code")
        if not code:
            continue
        BPMTemplate.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "name": bpm_row.get("name") or code,
                "diagram": bpm_row.get("diagram") or {},
                "steps": bpm_row.get("steps") or [],
            },
        )
        stats["bpm"] += 1

    for print_row in snap.get("print") or []:
        code = print_row.get("code")
        if not code:
            continue
        PrintTemplate.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "name": print_row.get("name") or code,
                "body": print_row.get("body") or "",
            },
        )
        stats["print"] += 1

    for nsi_row in snap.get("nsi") or []:
        code = nsi_row.get("code")
        if not code:
            continue
        clf, _ = NSIClassifier.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "name": nsi_row.get("name") or code,
                "description": nsi_row.get("description") or "",
                "is_active": nsi_row.get("is_active", True),
            },
        )
        for idx, vrow in enumerate(nsi_row.get("values") or [], start=1):
            vcode = vrow.get("code")
            if not vcode:
                continue
            NSIValue.objects.update_or_create(
                classifier=clf,
                code=vcode,
                defaults={
                    "name": vrow.get("name") or vcode,
                    "sort_order": vrow.get("sort_order", idx),
                },
            )
        stats["nsi"] += 1

    for int_row in snap.get("integrations") or []:
        code = int_row.get("code")
        if not code:
            continue
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code=code,
            defaults={
                "name": int_row.get("name") or code,
                "description": int_row.get("description") or "",
                "endpoint_type": int_row.get("endpoint_type")
                or IntegrationEndpoint.EndpointType.REST,
                "config": int_row.get("config") or {},
                "is_active": int_row.get("is_active", True),
                "max_retries": int_row.get("max_retries", 3),
            },
        )
        stats["integrations"] += 1

    if snap.get("policies"):
        _apply_policies(subsystem, snap["policies"])
        stats["policies"] = True

    return stats


def _apply_policies(subsystem, pol: dict) -> None:
    from delayu.services.retention import get_or_create_retention_policy
    from delayu.services.siem_export import get_or_create_siem_config

    retention = get_or_create_retention_policy(subsystem)
    if "retention_years" in pol:
        retention.default_archive_years = int(pol["retention_years"])
    if "alert_days" in pol:
        retention.alert_days_before = int(pol["alert_days"])
    if "auto_purge" in pol:
        retention.auto_purge_enabled = bool(pol["auto_purge"])
    retention.save()
    siem = get_or_create_siem_config(subsystem)
    if "siem_enabled" in pol:
        siem.enabled = bool(pol["siem_enabled"])
    if "siem_webhook_url" in pol:
        siem.webhook_url = pol["siem_webhook_url"] or ""
    siem.save()


def _revision_snapshot(subsystem, revision_id: int | None = None):
    if revision_id:
        return StudioConfigRevision.objects.filter(
            subsystem=subsystem, pk=revision_id
        ).first()
    return (
        StudioConfigRevision.objects.filter(subsystem=subsystem)
        .order_by("-created_at")
        .first()
    )


def baseline_form_schema(subsystem, form_code: str, *, revision_id: int | None = None) -> list:
    """Схема формы из опубликованной ревизии (последней или указанной)."""
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return []
    for row in (rev.snapshot or {}).get("forms") or []:
        if row.get("code") == form_code:
            return row.get("schema") or []
    return []


def baseline_menu_layout(subsystem, *, revision_id: int | None = None) -> list:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return []
    return (rev.snapshot or {}).get("menu_layout") or []


def baseline_bpm_template(subsystem, template_code: str, *, revision_id: int | None = None) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    for row in (rev.snapshot or {}).get("bpm") or []:
        if row.get("code") == template_code:
            return row
    return {}


def baseline_correspondence_workflow(subsystem, *, revision_id: int | None = None) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    return (rev.snapshot or {}).get("correspondence_workflow") or {}


def baseline_policies(subsystem, *, revision_id: int | None = None) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    return (rev.snapshot or {}).get("policies") or {}


def baseline_print_template(
    subsystem, template_code: str, *, revision_id: int | None = None
) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    for row in (rev.snapshot or {}).get("print") or []:
        if row.get("code") == template_code:
            return row
    return {}


def baseline_nsi_classifier(
    subsystem, classifier_code: str, *, revision_id: int | None = None
) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    for row in (rev.snapshot or {}).get("nsi") or []:
        if row.get("code") == classifier_code:
            return row
    return {}


def baseline_integration_endpoint(
    subsystem, endpoint_code: str, *, revision_id: int | None = None
) -> dict:
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        return {}
    for row in (rev.snapshot or {}).get("integrations") or []:
        if row.get("code") == endpoint_code:
            return row
    return {}


def current_policies_snapshot(subsystem) -> dict:
    from delayu.services.retention import get_or_create_retention_policy
    from delayu.services.siem_export import get_or_create_siem_config

    retention = get_or_create_retention_policy(subsystem)
    siem = get_or_create_siem_config(subsystem)
    return {
        "retention_years": retention.default_archive_years,
        "alert_days": retention.alert_days_before,
        "auto_purge": retention.auto_purge_enabled,
        "siem_enabled": siem.enabled,
        "siem_webhook": bool(siem.webhook_url),
        "siem_webhook_url": siem.webhook_url or "",
    }


def get_blueprint_package(blueprint_id: str) -> dict:
    bp = next((b for b in studio.STUDIO_BLUEPRINTS if b["id"] == blueprint_id), None)
    if not bp:
        raise ValueError("unknown blueprint")
    return {
        "format": "delayu-blueprint",
        "format_version": 1,
        "blueprint": bp,
    }


def apply_blueprint_package(
    subsystem,
    package: dict,
    *,
    role_map: dict | None = None,
) -> dict:
    """Применить шаблон из встроенного каталога или JSON-пакета."""
    from delayu.services.studio_package_validate import validate_blueprint_package

    bp = package.get("blueprint") if package.get("format") == "delayu-blueprint" else package
    if not bp:
        raise ValueError("empty blueprint")
    blueprint_id = bp.get("id")
    if blueprint_id and any(b["id"] == blueprint_id for b in studio.STUDIO_BLUEPRINTS):
        return apply_blueprint(subsystem, blueprint_id, role_map=role_map)
    if package.get("format") == "delayu-blueprint" or package.get("blueprint"):
        validation = validate_blueprint_package(package)
        if not validation["ok"]:
            raise ValueError("; ".join(validation["errors"]) or "Невалидный шаблон")
    applied = []
    role_layouts = 0
    if bp.get("menu"):
        save_draft(subsystem, "menu", bp["menu"])
        applied.append("menu")
    if bp.get("correspondence"):
        save_draft(subsystem, "correspondence", bp["correspondence"])
        applied.append("correspondence")
    if bp.get("role_layouts"):
        role_by_code = {r.code: r for r in Role.objects.filter(subsystem=subsystem)}
        mapping = role_map or {}
        for row in bp["role_layouts"]:
            code = mapping.get(row.get("role_code") or "", row.get("role_code") or "")
            role = role_by_code.get(code)
            if not role:
                continue
            save_role_layout(subsystem, role, row.get("kind") or "", row.get("widgets") or [])
            role_layouts += 1
        if role_layouts:
            applied.append("role_layouts")
    pending_tags = _queue_blueprint_publish_tags(subsystem, bp, blueprint_id or "custom")
    return {
        "blueprint": blueprint_id or "custom",
        "applied": applied,
        "role_layouts": role_layouts,
        "pending_publish_tags": pending_tags,
    }


def apply_blueprint(subsystem, blueprint_id: str, *, role_map: dict | None = None) -> dict:
    """Применить шаблон конфигурации в черновик меню/СЭД и ролевые раскладки."""
    bp = next((b for b in studio.STUDIO_BLUEPRINTS if b["id"] == blueprint_id), None)
    if not bp:
        raise ValueError("unknown blueprint")
    applied = []
    role_layouts = 0
    if bp.get("menu"):
        save_draft(subsystem, "menu", bp["menu"])
        applied.append("menu")
    if bp.get("correspondence"):
        save_draft(subsystem, "correspondence", bp["correspondence"])
        applied.append("correspondence")
    if bp.get("role_layouts"):
        role_by_code = {r.code: r for r in Role.objects.filter(subsystem=subsystem)}
        mapping = role_map or {}
        for row in bp["role_layouts"]:
            src = row.get("role_code") or ""
            code = mapping.get(src, src)
            role = role_by_code.get(code)
            if not role:
                continue
            save_role_layout(subsystem, role, row.get("kind") or "", row.get("widgets") or [])
            role_layouts += 1
        if role_layouts:
            applied.append("role_layouts")
    pending_tags = _queue_blueprint_publish_tags(subsystem, bp, blueprint_id)
    return {
        "blueprint": blueprint_id,
        "applied": applied,
        "role_layouts": role_layouts,
        "pending_publish_tags": pending_tags,
    }


def preview_blueprint(subsystem, blueprint_id: str, *, role_map: dict | None = None) -> dict:
    """Предпросмотр шаблона без применения."""
    bp = next((b for b in studio.STUDIO_BLUEPRINTS if b["id"] == blueprint_id), None)
    if not bp:
        raise ValueError("unknown blueprint")
    role_by_code = {r.code: r for r in Role.objects.filter(subsystem=subsystem)}
    mapping = role_map or {}
    menu = bp.get("menu") or []
    menu_items = sum(len(sec.get("items") or []) for sec in menu if isinstance(sec, dict))
    corr = bp.get("correspondence") or {}
    role_layouts = []
    for row in bp.get("role_layouts") or []:
        src = row.get("role_code") or ""
        target = mapping.get(src, src)
        role = role_by_code.get(target)
        role_layouts.append(
            {
                "role_code": src,
                "mapped_to": target,
                "kind": row.get("kind") or "",
                "widgets": row.get("widgets") or [],
                "resolved": bool(role),
                "role_name": role.name if role else "",
            }
        )
    return {
        "ok": True,
        "blueprint": blueprint_id,
        "name": bp.get("name") or blueprint_id,
        "description": bp.get("description") or "",
        "draft_sections": [k for k in ("menu", "correspondence") if bp.get(k)],
        "menu_sections": len(menu),
        "menu_items": menu_items,
        "correspondence_steps": list(corr.get("steps") or []),
        "sla_days": corr.get("sla_days") or {},
        "role_layouts": role_layouts,
        "role_layouts_resolved": sum(1 for r in role_layouts if r["resolved"]),
    }


def dry_run_blueprint(subsystem, blueprint_id: str, *, role_map: dict | None = None) -> dict:
    """Предпросмотр влияния шаблона на текущую конфигурацию без применения."""
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    bp = next((b for b in studio.STUDIO_BLUEPRINTS if b["id"] == blueprint_id), None)
    if not bp:
        raise ValueError("unknown blueprint")
    preview = preview_blueprint(subsystem, blueprint_id, role_map=role_map)
    current = effective_snapshot(subsystem)
    simulated = _simulate_blueprint_snapshot(subsystem, bp, role_map=role_map, base=current)
    diff = compare_snapshots_detailed(current, simulated)
    return {
        **preview,
        "dry_run": True,
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
        "overwrites_draft": bool(subsystem.studio_has_draft),
    }


def _simulate_blueprint_snapshot(subsystem, bp: dict, *, role_map: dict | None = None, base: dict | None = None) -> dict:
    """Снимок конфигурации после применения шаблона (без записи в БД)."""
    simulated = dict(base or effective_snapshot(subsystem))
    if bp.get("menu"):
        simulated["menu_layout"] = bp["menu"]
    if bp.get("correspondence"):
        simulated["correspondence_workflow"] = bp["correspondence"]
    return simulated


def dry_run_blueprint_package(subsystem, package: dict, *, role_map: dict | None = None) -> dict:
    """Dry-run произвольного JSON-шаблона (delayu-blueprint)."""
    from delayu.services.studio_package_validate import validate_blueprint_package
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    validation = validate_blueprint_package(package)
    if not validation["ok"]:
        return {"ok": False, "validation": validation, "errors": validation["errors"]}
    bp = package.get("blueprint") or package
    blueprint_id = bp.get("id") or "custom"
    current = effective_snapshot(subsystem)
    simulated = _simulate_blueprint_snapshot(subsystem, bp, role_map=role_map, base=current)
    diff = compare_snapshots_detailed(current, simulated)
    preview = preview_blueprint(subsystem, blueprint_id, role_map=role_map) if any(
        b["id"] == blueprint_id for b in studio.STUDIO_BLUEPRINTS
    ) else {
        "ok": True,
        "blueprint": blueprint_id,
        "name": bp.get("name") or blueprint_id,
        "description": bp.get("description") or "",
        "draft_sections": [k for k in ("menu", "correspondence") if bp.get(k)],
    }
    return {
        **preview,
        "ok": True,
        "dry_run": True,
        "validation": validation,
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
        "overwrites_draft": bool(subsystem.studio_has_draft),
    }


_PINNED_REVISIONS_KEY = "pinned_revisions"
_REVISION_TAGS_KEY = "revision_tags"
_DEFAULT_PUBLISH_TAGS_KEY = "default_publish_tags"
_PENDING_PUBLISH_TAGS_KEY = "pending_publish_tags"


def get_revision_tags_map(subsystem) -> dict[int, list[str]]:
    raw = (subsystem.studio_setup_state or {}).get(_REVISION_TAGS_KEY) or {}
    result: dict[int, list[str]] = {}
    for key, value in raw.items():
        if not str(key).isdigit():
            continue
        tags = value if isinstance(value, list) else []
        cleaned = [str(t).strip() for t in tags if str(t).strip()][:10]
        if cleaned:
            result[int(key)] = cleaned
    return result


def set_revision_tags(subsystem, revision_id: int, tags: list) -> list[str]:
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    state = dict(subsystem.studio_setup_state or {})
    tag_map = dict(state.get(_REVISION_TAGS_KEY) or {})
    key = str(int(revision_id))
    if cleaned:
        tag_map[key] = cleaned
    else:
        tag_map.pop(key, None)
    state[_REVISION_TAGS_KEY] = tag_map
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return cleaned


def list_revision_tags(subsystem) -> list[str]:
    """Уникальные теги ревизий подсистемы."""
    seen: set[str] = set()
    result: list[str] = []
    for tags in get_revision_tags_map(subsystem).values():
        for tag in tags:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(tag)
    return sorted(result, key=str.lower)


def list_publish_tag_suggestions(subsystem) -> list[str]:
    """Подсказки для полей тегов публикации."""
    seen: set[str] = set()
    result: list[str] = []
    for src in (
        list_revision_tags(subsystem),
        get_default_publish_tags(subsystem),
        get_pending_publish_tags(subsystem),
    ):
        for tag in src:
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(tag)
    return sorted(result, key=str.lower)


def get_default_publish_tags(subsystem) -> list[str]:
    raw = (subsystem.studio_setup_state or {}).get(_DEFAULT_PUBLISH_TAGS_KEY) or []
    return [str(t).strip() for t in raw if str(t).strip()][:10]


def set_default_publish_tags(subsystem, tags: list) -> list[str]:
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    state = dict(subsystem.studio_setup_state or {})
    state[_DEFAULT_PUBLISH_TAGS_KEY] = cleaned
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return cleaned


def get_pending_publish_tags(subsystem) -> list[str]:
    raw = (subsystem.studio_setup_state or {}).get(_PENDING_PUBLISH_TAGS_KEY) or []
    return [str(t).strip() for t in raw if str(t).strip()][:10]


def set_pending_publish_tags(subsystem, tags: list) -> list[str]:
    cleaned = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    state = dict(subsystem.studio_setup_state or {})
    state[_PENDING_PUBLISH_TAGS_KEY] = cleaned
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return cleaned


def clear_pending_publish_tags(subsystem) -> None:
    state = dict(subsystem.studio_setup_state or {})
    if _PENDING_PUBLISH_TAGS_KEY in state:
        state.pop(_PENDING_PUBLISH_TAGS_KEY, None)
        subsystem.studio_setup_state = state
        subsystem.save(update_fields=["studio_setup_state", "updated_at"])


def merge_publish_tags(subsystem, explicit: list | None) -> list[str]:
    """Объединить явные теги, pending (после шаблона) и теги по умолчанию."""
    return preview_publish_tags(subsystem, explicit)["merged"]


def preview_publish_tags(subsystem, explicit: list | None = None) -> dict:
    """Разбор тегов публикации: явные, pending, по умолчанию и итог."""
    explicit_list = [str(t).strip() for t in (explicit or []) if str(t).strip()]
    pending = get_pending_publish_tags(subsystem)
    defaults = get_default_publish_tags(subsystem)
    merged = list(dict.fromkeys(explicit_list + pending + defaults))[:10]
    return {
        "explicit": explicit_list,
        "pending": pending,
        "default": defaults,
        "merged": merged,
    }


def _queue_blueprint_publish_tags(subsystem, bp: dict, blueprint_id: str | None) -> list[str]:
    bp_tags = [str(t).strip() for t in (bp.get("publish_tags") or []) if str(t).strip()]
    if not bp_tags and blueprint_id:
        bp_tags = [blueprint_id]
    if not bp_tags:
        return get_pending_publish_tags(subsystem)
    merged = list(dict.fromkeys(get_pending_publish_tags(subsystem) + bp_tags))[:10]
    set_pending_publish_tags(subsystem, merged)
    return merged


def get_revision_ids_by_tag(subsystem, tag: str) -> list[int]:
    """ID ревизий с указанным тегом (без учёта регистра)."""
    tag_lower = (tag or "").strip().lower()
    if not tag_lower:
        return []
    return [
        rid
        for rid, tags in get_revision_tags_map(subsystem).items()
        if any(t.lower() == tag_lower for t in tags)
    ]


def filter_studio_audit_by_revision_tag(qs, subsystem, tag: str):
    """Ограничить журнал studio.* событиями ревизий с тегом."""
    from django.db.models import Q

    rev_ids = get_revision_ids_by_tag(subsystem, tag)
    if not rev_ids:
        return qs.none()
    id_strs = [str(rid) for rid in rev_ids]
    versions = list(
        StudioConfigRevision.objects.filter(pk__in=rev_ids).values_list(
            "version_label", flat=True
        )
    )
    return qs.filter(Q(object_id__in=id_strs) | Q(payload__version__in=versions))


def bulk_set_revision_tags(
    subsystem,
    revision_ids: list,
    tags: list,
    *,
    mode: str = "set",
) -> dict:
    """Массовое изменение тегов: set | add | remove."""
    mode = mode if mode in ("set", "add", "remove") else "set"
    cleaned_tags = [str(t).strip() for t in (tags or []) if str(t).strip()][:10]
    remove_keys = {t.lower() for t in cleaned_tags}
    updated: list[int] = []
    for raw_id in revision_ids or []:
        if not str(raw_id).isdigit():
            continue
        rev_id = int(raw_id)
        if not StudioConfigRevision.objects.filter(pk=rev_id, subsystem=subsystem).exists():
            continue
        if mode == "set":
            set_revision_tags(subsystem, rev_id, cleaned_tags)
        elif mode == "add":
            existing = get_revision_tags_map(subsystem).get(rev_id, [])
            merged = list(dict.fromkeys(existing + cleaned_tags))[:10]
            set_revision_tags(subsystem, rev_id, merged)
        else:
            existing = get_revision_tags_map(subsystem).get(rev_id, [])
            remaining = [t for t in existing if t.lower() not in remove_keys]
            set_revision_tags(subsystem, rev_id, remaining)
        updated.append(rev_id)
    return {
        "ok": True,
        "updated": updated,
        "count": len(updated),
        "mode": mode,
        "tags": cleaned_tags,
    }


def update_revision_comment(subsystem, revision_id: int, comment: str) -> StudioConfigRevision:
    rev = StudioConfigRevision.objects.filter(pk=revision_id, subsystem=subsystem).first()
    if not rev:
        raise ValueError("revision not found")
    rev.comment = (comment or "")[:255]
    rev.save(update_fields=["comment"])
    return rev


def update_revision_meta(
    subsystem,
    revision_id: int,
    *,
    comment: str | None = None,
    tags: list | None = None,
) -> dict:
    """Обновить комментарий и/или теги ревизии."""
    rev = StudioConfigRevision.objects.filter(pk=revision_id, subsystem=subsystem).first()
    if not rev:
        raise ValueError("revision not found")
    if comment is not None:
        rev.comment = (comment or "")[:255]
        rev.save(update_fields=["comment"])
    tag_list = get_revision_tags_map(subsystem).get(rev.pk, [])
    if tags is not None:
        tag_list = set_revision_tags(subsystem, rev.pk, tags)
    return {
        "ok": True,
        "revision_id": rev.pk,
        "version_label": rev.version_label,
        "comment": rev.comment or "",
        "tags": tag_list,
    }


def get_pinned_revision_ids(subsystem) -> list[int]:
    raw = (subsystem.studio_setup_state or {}).get(_PINNED_REVISIONS_KEY) or []
    return [int(x) for x in raw if str(x).isdigit()]


def set_revision_pinned(subsystem, revision_id: int, *, pinned: bool = True) -> list[int]:
    state = dict(subsystem.studio_setup_state or {})
    ids = {int(x) for x in state.get(_PINNED_REVISIONS_KEY) or [] if str(x).isdigit()}
    if pinned:
        ids.add(int(revision_id))
    else:
        ids.discard(int(revision_id))
    state[_PINNED_REVISIONS_KEY] = sorted(ids)
    subsystem.studio_setup_state = state
    subsystem.save(update_fields=["studio_setup_state", "updated_at"])
    return list(state[_PINNED_REVISIONS_KEY])


def prune_studio_revisions(
    subsystem,
    *,
    keep: int = 50,
    dry_run: bool = False,
) -> dict:
    """Удалить старые ревизии, оставив keep последних (+ закреплённые)."""
    keep = max(1, min(int(keep or 50), 500))
    pinned = set(get_pinned_revision_ids(subsystem))
    qs = StudioConfigRevision.objects.filter(subsystem=subsystem).order_by("-created_at")
    keep_ids = set(qs[:keep].values_list("pk", flat=True)) | pinned
    to_delete = qs.exclude(pk__in=keep_ids)
    delete_count = to_delete.count()
    labels = list(to_delete.values_list("version_label", flat=True)[:20])
    if not dry_run and delete_count:
        to_delete.delete()
    return {
        "ok": True,
        "dry_run": dry_run,
        "keep": keep,
        "pinned": sorted(pinned),
        "would_delete": delete_count,
        "deleted": 0 if dry_run else delete_count,
        "sample_labels": labels,
        "remaining": StudioConfigRevision.objects.filter(subsystem=subsystem).count(),
    }


def list_studio_revisions(
    subsystem,
    *,
    limit: int = 20,
    offset: int = 0,
    tag: str = "",
    q: str = "",
) -> dict:
    """Список ревизий: закреплённые первыми, фильтр по тегу и поиску."""
    limit = max(1, min(int(limit or 20), 200))
    offset = max(0, int(offset or 0))
    tag_filter = (tag or "").strip().lower()
    query = (q or "").strip().lower()
    pinned = set(get_pinned_revision_ids(subsystem))
    tag_map = get_revision_tags_map(subsystem)
    qs = (
        StudioConfigRevision.objects.filter(subsystem=subsystem)
        .select_related("published_by")
        .order_by("-created_at")
    )
    revs = list(qs)
    if tag_filter:
        matching = {
            rid
            for rid, tags in tag_map.items()
            if any(t.lower() == tag_filter for t in tags)
        }
        revs = [r for r in revs if r.pk in matching]
    if query:
        revs = [
            r
            for r in revs
            if query in (r.comment or "").lower()
            or query in (r.version_label or "").lower()
            or any(query in t.lower() for t in tag_map.get(r.pk, []))
        ]
    total = len(revs)
    revs.sort(key=lambda r: (0 if r.pk in pinned else 1, -r.pk))
    page = revs[offset : offset + limit]
    return {
        "ok": True,
        "total": total,
        "offset": offset,
        "limit": limit,
        "tag": tag_filter,
        "q": query,
        "pinned_ids": sorted(pinned),
        "available_tags": list_revision_tags(subsystem),
        "items": [
            {
                "id": rev.pk,
                "version_label": rev.version_label,
                "comment": rev.comment or "",
                "created_at": rev.created_at.isoformat() if rev.created_at else "",
                "published_by": (
                    rev.published_by.get_username() if rev.published_by_id else ""
                ),
                "pinned": rev.pk in pinned,
                "tags": tag_map.get(rev.pk, []),
            }
            for rev in page
        ],
    }


def compare_blueprint_with_live(
    subsystem,
    blueprint_id: str,
    *,
    role_map: dict | None = None,
) -> dict:
    """Diff: текущая опубликованная конфигурация vs симуляция шаблона."""
    result = dry_run_blueprint(subsystem, blueprint_id, role_map=role_map)
    if result.get("ok"):
        result["compare_with"] = "live"
        result["live_version"] = subsystem.config_version or ""
    return result


def compare_blueprint_with_revision(
    subsystem,
    blueprint_id: str,
    revision_id: int,
    *,
    role_map: dict | None = None,
) -> dict:
    """Diff: снимок ревизии vs конфигурация после применения шаблона."""
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    bp = next((b for b in studio.STUDIO_BLUEPRINTS if b["id"] == blueprint_id), None)
    if not bp:
        raise ValueError("unknown blueprint")
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        raise ValueError("revision not found")
    before = rev.snapshot or {}
    simulated = _simulate_blueprint_snapshot(subsystem, bp, role_map=role_map)
    diff = compare_snapshots_detailed(before, simulated)
    preview = preview_blueprint(subsystem, blueprint_id, role_map=role_map)
    return {
        **preview,
        "ok": True,
        "revision_id": rev.pk,
        "revision_label": rev.version_label,
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
        "compare_with": "revision",
    }


def compare_blueprint_package_with_revision(
    subsystem,
    package: dict,
    revision_id: int,
    *,
    role_map: dict | None = None,
) -> dict:
    """Diff: снимок ревизии vs произвольный JSON-шаблон."""
    from delayu.services.studio_package_validate import validate_blueprint_package
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    validation = validate_blueprint_package(package)
    if not validation["ok"]:
        return {"ok": False, "validation": validation, "errors": validation["errors"]}
    bp = package.get("blueprint") or package
    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        raise ValueError("revision not found")
    before = rev.snapshot or {}
    simulated = _simulate_blueprint_snapshot(subsystem, bp, role_map=role_map)
    diff = compare_snapshots_detailed(before, simulated)
    blueprint_id = bp.get("id") or "custom"
    preview = preview_blueprint(subsystem, blueprint_id, role_map=role_map) if any(
        b["id"] == blueprint_id for b in studio.STUDIO_BLUEPRINTS
    ) else {
        "ok": True,
        "blueprint": blueprint_id,
        "name": bp.get("name") or blueprint_id,
        "description": bp.get("description") or "",
        "draft_sections": [k for k in ("menu", "correspondence") if bp.get(k)],
    }
    return {
        **preview,
        "ok": True,
        "validation": validation,
        "revision_id": rev.pk,
        "revision_label": rev.version_label,
        "compare_with": "revision",
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
    }


def compare_blueprint_package_with_live(
    subsystem,
    package: dict,
    *,
    role_map: dict | None = None,
) -> dict:
    """Diff: текущая конфигурация vs произвольный JSON-шаблон."""
    from delayu.services.studio_package_validate import validate_blueprint_package
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    validation = validate_blueprint_package(package)
    if not validation["ok"]:
        return {"ok": False, "validation": validation, "errors": validation["errors"]}
    bp = package.get("blueprint") or package
    blueprint_id = bp.get("id") or "custom"
    current = effective_snapshot(subsystem)
    simulated = _simulate_blueprint_snapshot(subsystem, bp, role_map=role_map, base=current)
    diff = compare_snapshots_detailed(current, simulated)
    preview = preview_blueprint(subsystem, blueprint_id, role_map=role_map) if any(
        b["id"] == blueprint_id for b in studio.STUDIO_BLUEPRINTS
    ) else {
        "ok": True,
        "blueprint": blueprint_id,
        "name": bp.get("name") or blueprint_id,
        "description": bp.get("description") or "",
        "draft_sections": [k for k in ("menu", "correspondence") if bp.get(k)],
    }
    return {
        **preview,
        "ok": True,
        "validation": validation,
        "compare_with": "live",
        "live_version": subsystem.config_version or "",
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
    }


def export_revisions_archive(
    subsystem,
    *,
    max_revisions: int = 500,
    tag: str = "",
    pinned_only: bool = False,
    q: str = "",
):
    """ZIP-архив ревизий (фильтр по тегу, поиску или только закреплённые)."""
    import io
    import json
    import zipfile

    from django.http import HttpResponse

    max_revisions = max(1, min(int(max_revisions or 500), 1000))
    tag_filter = (tag or "").strip().lower()
    query = (q or "").strip().lower()
    pinned = set(get_pinned_revision_ids(subsystem))
    tag_map = get_revision_tags_map(subsystem)
    revs = list(
        StudioConfigRevision.objects.filter(subsystem=subsystem)
        .select_related("published_by", "subsystem")
        .order_by("-created_at")
    )
    if pinned_only:
        revs = [r for r in revs if r.pk in pinned]
    if tag_filter:
        matching = {
            rid
            for rid, tags in tag_map.items()
            if any(t.lower() == tag_filter for t in tags)
        }
        revs = [r for r in revs if r.pk in matching]
    if query:
        revs = [
            r
            for r in revs
            if query in (r.comment or "").lower()
            or query in (r.version_label or "").lower()
            or any(query in t.lower() for t in tag_map.get(r.pk, []))
        ]
    revs = revs[:max_revisions]
    stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO()
    manifest = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rev in revs:
            pkg = export_revision_package(rev)
            pkg["tags"] = tag_map.get(rev.pk, [])
            pkg["pinned"] = rev.pk in pinned
            safe_label = (rev.version_label or str(rev.pk)).replace("/", "_").replace("\\", "_")
            fname = f"revisions/{safe_label}_{rev.pk}.json"
            zf.writestr(fname, json.dumps(pkg, ensure_ascii=False, indent=2))
            manifest.append(
                {
                    "id": rev.pk,
                    "version_label": rev.version_label,
                    "file": fname,
                    "pinned": rev.pk in pinned,
                    "tags": tag_map.get(rev.pk, []),
                    "comment": rev.comment or "",
                    "created_at": rev.created_at.isoformat() if rev.created_at else "",
                }
            )
        zf.writestr(
            "revision-meta.json",
            json.dumps(
                {
                    "pinned_revision_ids": sorted(pinned),
                    "revision_tags": {str(k): v for k, v in tag_map.items()},
                    "tag_index": list_revision_tags(subsystem),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        zf.writestr(
            "manifest.json",
            json.dumps(
                {
                    "format": "delayu-studio-revisions-archive",
                    "format_version": 3,
                    "exported_at": timezone.now().isoformat(),
                    "subsystem": subsystem.code,
                    "count": len(manifest),
                    "tag_filter": tag_filter,
                    "query": query,
                    "pinned_only": pinned_only,
                    "pinned": sorted(pinned),
                    "revisions": manifest,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    resp = HttpResponse(buf.getvalue(), content_type="application/zip")
    resp["Content-Disposition"] = (
        f'attachment; filename="studio-revisions-{subsystem.code}-{stamp}.zip"'
    )
    return resp


def dry_run_import_package(subsystem, package: dict, *, to_draft: bool = True) -> dict:
    """Сравнение импортируемого пакета с текущим состоянием без применения."""
    from delayu.services.studio_import_risk import evaluate_import_risk
    from delayu.services.studio_package_validate import validate_config_package
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    validation = validate_config_package(package)
    if not validation["ok"]:
        return {"ok": False, "validation": validation, "errors": validation["errors"]}
    incoming = package.get("snapshot") or package
    if not isinstance(incoming, dict):
        raise ValueError("empty package")
    current = effective_snapshot(subsystem, include_draft=to_draft)
    diff = compare_snapshots_detailed(current, incoming)
    stats = {
        "forms": len(incoming.get("forms") or []),
        "bpm": len(incoming.get("bpm") or []),
        "print": len(incoming.get("print") or []),
        "nsi": len(incoming.get("nsi") or []),
        "integrations": len(incoming.get("integrations") or []),
        "role_layouts": len(incoming.get("role_layouts") or []),
        "has_menu": incoming.get("menu_layout") is not None,
        "has_correspondence": incoming.get("correspondence_workflow") is not None,
        "has_policies": bool(incoming.get("policies")),
        "to_draft": to_draft,
        "package_draft": bool(package.get("studio_has_draft")),
    }
    return {
        "ok": True,
        "validation": validation,
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "stats": stats,
        "risk": evaluate_import_risk(current, incoming),
        "has_detail_changes": diff.get("has_detail_changes"),
    }


def compare_with_revision(subsystem, revision_id: int | None, *, include_draft: bool = True) -> dict:
    """Сравнение текущего состояния (или с черновиком) с ревизией."""
    from delayu.services.studio_revision_compare import compare_snapshots_detailed

    rev = _revision_snapshot(subsystem, revision_id)
    if not rev:
        raise ValueError("revision not found")
    before = rev.snapshot or {}
    after = effective_snapshot(subsystem, include_draft=include_draft)
    diff = compare_snapshots_detailed(before, after)
    return {
        "ok": True,
        "revision_label": rev.version_label,
        "revision_id": rev.pk,
        "include_draft": include_draft,
        "diff": diff,
        "entity_diffs": diff.get("entity_diffs") or {},
        "policies_diff": diff.get("policies_diff") or {},
        "has_detail_changes": diff.get("has_detail_changes"),
    }


def export_revision_package(revision: StudioConfigRevision) -> dict:
    """JSON-снимок одной ревизии для архива или переноса."""
    publisher = ""
    if revision.published_by_id:
        publisher = (
            revision.published_by.get_full_name() or revision.published_by.username
        )
    return {
        "format": "delayu-studio-revision",
        "format_version": 1,
        "exported_at": timezone.now().isoformat(),
        "revision_id": revision.pk,
        "version_label": revision.version_label,
        "comment": revision.comment or "",
        "published_by": publisher,
        "published_at": revision.created_at.isoformat() if revision.created_at else "",
        "subsystem": {
            "code": revision.subsystem.code,
            "name": revision.subsystem.name,
        },
        "snapshot": revision.snapshot or {},
    }


def studio_summary(subsystem) -> dict:
    """Сводка состояния Студии для hub/API."""
    from delayu.models_business import AuditLog
    from delayu.services.studio_publish_schedule import get_scheduled_publish

    checks = subsystem_health_checks(subsystem)
    latest = (
        StudioConfigRevision.objects.filter(subsystem=subsystem)
        .order_by("-created_at")
        .first()
    )
    pinned = get_pinned_revision_ids(subsystem)
    from datetime import timedelta

    activity_7d = AuditLog.objects.filter(
        subsystem=subsystem,
        action__startswith="studio.",
        created_at__gte=timezone.now() - timedelta(days=7),
    ).count()
    from delayu.services.studio_activity_schedule import get_activity_digest_schedule
    from delayu.services.studio_compliance_schedule import get_compliance_export_schedule

    digest_sched = get_activity_digest_schedule(subsystem) or {}
    compliance_sched = get_compliance_export_schedule(subsystem) or {}
    return {
        "ok": True,
        "config_version": subsystem.config_version or "",
        "has_draft": subsystem.studio_has_draft,
        "published_at": subsystem.published_at.isoformat() if subsystem.published_at else "",
        "revisions": StudioConfigRevision.objects.filter(subsystem=subsystem).count(),
        "pinned_revisions": len(pinned),
        "activity_7d": activity_7d,
        "activity_digest_enabled": bool(digest_sched.get("enabled")),
        "activity_digest_interval_days": digest_sched.get("interval_days") or 0,
        "compliance_export_enabled": bool(compliance_sched.get("enabled")),
        "compliance_export_interval_days": compliance_sched.get("interval_days") or 0,
        "revision_tags": list_revision_tags(subsystem),
        "default_publish_tags": get_default_publish_tags(subsystem),
        "pending_publish_tags": get_pending_publish_tags(subsystem),
        "forced_ops": AuditLog.objects.filter(
            subsystem=subsystem,
            action__in=("studio.import", "studio.restore"),
            payload__forced=True,
        ).count(),
        "audit_total": AuditLog.objects.filter(
            subsystem=subsystem, action__startswith="studio."
        ).count(),
        "health": health_summary(checks),
        "last_publish": latest.version_label if latest else "",
        "last_publish_at": latest.created_at.isoformat() if latest else "",
        "scheduled_publish": get_scheduled_publish(subsystem),
    }


def restore_revision(
    subsystem,
    revision: StudioConfigRevision,
    user,
    *,
    mode: str = "draft",
    force: bool = False,
) -> dict:
    """Откат к снимку ревизии: в черновик или с немедленной публикацией."""
    from delayu.services.studio_import_risk import ImportRiskError, evaluate_restore_risk

    snap = revision.snapshot or {}
    current = effective_snapshot(subsystem, include_draft=True)
    risk = evaluate_restore_risk(current, snap)
    if risk["blocked"] and not force:
        raise ImportRiskError(risk)
    if mode == "draft":
        stats = apply_snapshot(subsystem, snap, to_draft=True)
        from delayu.services.studio_publish_events import on_studio_config_restored

        on_studio_config_restored(
            subsystem,
            revision,
            user,
            mode="draft",
            from_version=revision.version_label,
            forced=force,
            restore_risk=risk,
        )
        return {
            "mode": "draft",
            "stats": stats,
            "from_version": revision.version_label,
            "restore_risk": risk,
        }

    stats = apply_snapshot(subsystem, snap, to_draft=False)
    subsystem.studio_draft = {}
    subsystem.studio_has_draft = False
    version = next_version_label(subsystem)
    subsystem.config_version = version
    subsystem.published_at = timezone.now()
    subsystem.save(
        update_fields=[
            "menu_layout",
            "correspondence_workflow",
            "studio_draft",
            "studio_has_draft",
            "config_version",
            "published_at",
            "updated_at",
        ]
    )
    new_rev = StudioConfigRevision.objects.create(
        subsystem=subsystem,
        version_label=version,
        snapshot=capture_snapshot(subsystem),
        comment=f"Откат к {revision.version_label}"[:255],
        published_by=user,
    )
    from delayu.services.studio_publish_events import on_studio_config_restored

    on_studio_config_restored(
        subsystem,
        revision,
        user,
        mode="apply",
        from_version=revision.version_label,
        forced=force,
        new_revision=new_rev,
        restore_risk=risk,
    )
    return {
        "mode": "apply",
        "stats": stats,
        "from_version": revision.version_label,
        "version": new_rev.version_label,
        "revision_id": new_rev.pk,
        "restore_risk": risk,
    }
