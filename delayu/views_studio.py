"""Студия ДелаЮ — визуальные конструкторы (drag-and-drop)."""
import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from delayu.mixins import ModulePermissionMixin
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
    UserDashboardLayout,
    UserProfile,
)
from delayu.services import audit, studio
from delayu.services import studio_admin
from delayu.services.access import user_can
from delayu.services.form_schemas import sync_registry_form_schema
from delayu.services.roles import (
    PERM_ACTIONS,
    build_matrix_rows,
    enabled_modules_for_subsystem,
    permissions_from_post,
    save_role_permissions,
)
from delayu.views_platform import _ctx_membership


STUDIO_EDITORS = [
    {"slug": "preview", "title": "Просмотр как роль", "module": "M01", "icon": "ri-eye-line"},
    {"slug": "forms", "title": "Карточка дела / формы", "module": "M74", "icon": "ri-layout-4-line"},
    {"slug": "bpm", "title": "BPMN-процессы", "module": "M33", "icon": "ri-flow-chart"},
    {"slug": "menu", "title": "Меню подсистемы", "module": "M01", "icon": "ri-menu-line"},
    {"slug": "dashboard", "title": "Дашборд руководителя", "module": "M85", "icon": "ri-bar-chart-line"},
    {"slug": "today", "title": "Мне на сегодня", "module": "M08", "icon": "ri-calendar-check-line"},
    {"slug": "correspondence", "title": "Маршрут СЭД", "module": "M27", "icon": "ri-mail-send-line"},
    {"slug": "print", "title": "Печатные формы", "module": "M29", "icon": "ri-printer-line"},
    {"slug": "permissions", "title": "Матрица прав", "module": "M02", "icon": "ri-shield-user-line"},
    {"slug": "nsi", "title": "Справочники НСИ", "module": "M73", "icon": "ri-list-check"},
    {"slug": "integration", "title": "Pipeline интеграций", "module": "M42", "icon": "ri-plug-line"},
    {"slug": "policies", "title": "Политики хранения", "module": "M78", "icon": "ri-archive-line"},
    {"slug": "cabinet", "title": "Личный кабинет", "module": "M07", "icon": "ri-user-settings-line"},
]


STUDIO_URLS = {
    "preview": "platform-studio-preview",
    "forms": "platform-studio-forms",
    "bpm": "platform-studio-bpm",
    "menu": "platform-studio-menu",
    "dashboard": "platform-studio-dashboard",
    "today": "platform-studio-today",
    "correspondence": "platform-studio-correspondence",
    "print": "platform-studio-print",
    "permissions": "platform-studio-permissions",
    "nsi": "platform-studio-nsi",
    "integration": "platform-studio-integration",
    "policies": "platform-studio-policies",
    "cabinet": "platform-studio-cabinet",
}


class StudioMixin(ModulePermissionMixin):
    module_code = "M01"
    required_action = "change"
    studio_slug = ""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["studio_editors"] = [
            {**e, "url": reverse(STUDIO_URLS[e["slug"]])} for e in STUDIO_EDITORS
        ]
        ctx["studio_active"] = self.studio_slug
        ctx["breadcrumbs"] = [
            {"label": "Студия ДелаЮ", "url": reverse("platform-studio")},
            {"label": next((e["title"] for e in STUDIO_EDITORS if e["slug"] == self.studio_slug), ""), "url": None},
        ]
        return ctx


STUDIO_AUDIT_ACTIONS = [
    ("", "Все действия Студии"),
    ("studio.publish", "Публикация"),
    ("studio.import", "Импорт пакета"),
    ("studio.restore", "Откат ревизии"),
    ("studio.clone_config", "Клонирование (источник)"),
    ("studio.clone_import", "Клонирование (цель)"),
    ("studio.blueprint", "Шаблон"),
    ("studio.dry_run.package", "Dry-run пакета"),
    ("studio.dry_run.blueprint", "Dry-run шаблона"),
    ("studio.dry_run.publish", "Dry-run публикации"),
    ("studio.dry_run.restore", "Dry-run отката"),
    ("studio.dry_run.schedule", "Dry-run планирования"),
    ("studio.compare_revisions", "Сравнение ревизий"),
    ("studio.blueprint_compare", "Шаблон vs ревизия"),
    ("studio.export_revision", "Экспорт ревизии"),
    ("studio.prune_revisions", "Очистка ревизий"),
    ("studio.pin_revision", "Закрепление ревизии"),
    ("studio.revision_meta", "Метаданные ревизии"),
    ("studio.export_revisions", "Экспорт всех ревизий"),
    ("studio.activity_digest", "Сводка активности (увед.)"),
    ("studio.schedule_publish", "Планирование публикации"),
    ("studio.forced_import", "Принудительный импорт (увед.)"),
    ("studio.scheduled_publish_done", "Публикация по расписанию"),
]


class StudioHubView(StudioMixin, TemplateView):
    studio_slug = "hub"
    template_name = "platform/studio/hub.html"

    def get(self, request, *args, **kwargs):
        from delayu.services.studio_setup import should_auto_launch_setup

        membership = _ctx_membership(self)
        if (
            should_auto_launch_setup(membership.subsystem)
            and request.GET.get("skip_setup") != "1"
        ):
            return redirect(reverse("platform-studio-setup"))
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Студия ДелаЮ"
        ctx["breadcrumbs"] = [{"label": "Студия ДелаЮ", "url": None}]
        checks = studio_admin.subsystem_health_checks(m.subsystem)
        ctx["studio_health_checks"] = checks
        ctx["studio_health_summary"] = studio_admin.health_summary(checks)
        pinned_ids = set(studio_admin.get_pinned_revision_ids(m.subsystem))
        tag_map = studio_admin.get_revision_tags_map(m.subsystem)
        rev_qs = list(
            StudioConfigRevision.objects.filter(subsystem=m.subsystem).select_related(
                "published_by"
            )
        )
        rev_tag_filter = (self.request.GET.get("rev_tag") or "").strip().lower()
        rev_q_filter = (self.request.GET.get("rev_q") or "").strip().lower()
        if rev_tag_filter:
            matching = {
                rid
                for rid, tags in tag_map.items()
                if any(t.lower() == rev_tag_filter for t in tags)
            }
            rev_qs = [r for r in rev_qs if r.pk in matching]
        if rev_q_filter:
            rev_qs = [
                r
                for r in rev_qs
                if rev_q_filter in (r.comment or "").lower()
                or rev_q_filter in (r.version_label or "").lower()
                or any(rev_q_filter in t.lower() for t in tag_map.get(r.pk, []))
            ]
        rev_qs.sort(key=lambda r: (0 if r.pk in pinned_ids else 1, -r.pk))
        for rev in rev_qs[:8]:
            rev.studio_tags = tag_map.get(rev.pk, [])
        ctx["studio_revisions"] = rev_qs[:8]
        ctx["studio_revision_tag_list"] = studio_admin.list_revision_tags(m.subsystem)
        ctx["studio_revision_tag_filter"] = rev_tag_filter
        ctx["studio_revision_q_filter"] = rev_q_filter
        ctx["studio_default_publish_tags"] = studio_admin.get_default_publish_tags(m.subsystem)
        ctx["studio_pending_publish_tags"] = studio_admin.get_pending_publish_tags(m.subsystem)
        ctx["studio_publish_tag_suggestions"] = studio_admin.list_publish_tag_suggestions(
            m.subsystem
        )
        ctx["studio_has_draft"] = m.subsystem.studio_has_draft
        ctx["studio_config_version"] = m.subsystem.config_version or "—"
        ctx["studio_published_at"] = m.subsystem.published_at
        ctx["studio_audit_url"] = reverse("platform-audit") + "?action=studio."
        ctx["studio_compare_url"] = reverse("platform-studio-revision-compare")
        ctx["studio_restore_url"] = reverse("platform-studio-revision-restore")
        ctx["studio_blueprint_url"] = reverse("platform-studio-blueprint-apply")
        ctx["studio_blueprint_preview_url"] = reverse("platform-studio-blueprint-preview")
        ctx["studio_blueprints"] = studio.STUDIO_BLUEPRINTS
        ctx["studio_roles"] = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        ctx["studio_blueprints_enriched"] = [
            {
                **bp,
                "role_codes": sorted(
                    {
                        row.get("role_code")
                        for row in bp.get("role_layouts") or []
                        if row.get("role_code")
                    }
                ),
            }
            for bp in studio.STUDIO_BLUEPRINTS
        ]
        from delayu.models_business import AuditLog

        ctx["studio_clone_log"] = list(
            AuditLog.objects.filter(
                subsystem=m.subsystem, action__in=("studio.clone_config", "studio.clone_import")
            )
            .select_related("user")
            .order_by("-created_at")[:6]
        )
        from delayu.services.studio_setup import setup_progress

        ctx["studio_setup"] = setup_progress(m.subsystem)
        ctx["studio_setup_url"] = reverse("platform-studio-setup")
        ctx["studio_clone_url"] = reverse("platform-studio-clone")
        ctx["studio_schedule_url"] = reverse("platform-studio-schedule-publish")
        ctx["studio_package_diff_url"] = reverse("platform-studio-package-diff")
        ctx["studio_package_validate_url"] = reverse("platform-studio-package-validate")
        ctx["studio_blueprint_validate_url"] = reverse("platform-studio-blueprint-validate")
        ctx["studio_audit_export_url"] = reverse("platform-studio-audit-export")
        ctx["studio_forced_export_url"] = reverse("platform-studio-forced-audit-export")
        ctx["studio_compliance_export_url"] = reverse("platform-studio-compliance-export")
        ctx["studio_compliance_schedule_url"] = reverse("platform-studio-compliance-schedule")
        ctx["studio_summary_url"] = reverse("platform-studio-summary")
        ctx["studio_compare_export_url"] = reverse("platform-studio-revision-compare-export")
        ctx["studio_activity_url"] = reverse("platform-studio-activity")
        ctx["studio_activity_export_url"] = reverse("platform-studio-activity-export")
        ctx["studio_revision_prune_url"] = reverse("platform-studio-revision-prune")
        ctx["studio_revision_pin_url"] = reverse("platform-studio-revision-pin")
        ctx["studio_revision_meta_url"] = reverse("platform-studio-revision-meta")
        ctx["studio_revision_bulk_tags_url"] = reverse("platform-studio-revision-bulk-tags")
        ctx["studio_revisions_list_url"] = reverse("platform-studio-revisions-list")
        ctx["studio_activity_notify_url"] = reverse("platform-studio-activity-notify")
        ctx["studio_activity_schedule_url"] = reverse("platform-studio-activity-schedule")
        ctx["studio_blueprint_compare_url"] = reverse("platform-studio-blueprint-compare")
        ctx["studio_blueprint_compare_live_url"] = reverse("platform-studio-blueprint-compare-live")
        ctx["studio_blueprint_package_compare_url"] = reverse("platform-studio-blueprint-package-compare")
        ctx["studio_schedule_dry_run_url"] = reverse("platform-studio-schedule-dry-run")
        ctx["studio_publish_dry_run_url"] = reverse("platform-studio-publish-dry-run")
        ctx["studio_publish_default_tags_url"] = reverse("platform-studio-publish-default-tags")
        ctx["studio_clear_pending_tags_url"] = reverse("platform-studio-clear-pending-tags")
        ctx["studio_restore_dry_run_url"] = reverse("platform-studio-revision-restore-dry-run")
        audit_action = self.request.GET.get("audit_action", "").strip()
        forced_only = self.request.GET.get("forced") == "1"
        audit_rev_tag = (self.request.GET.get("audit_rev_tag") or "").strip()
        audit_qs = AuditLog.objects.filter(
            subsystem=m.subsystem, action__startswith="studio."
        )
        if audit_action:
            audit_qs = audit_qs.filter(action=audit_action)
        if forced_only:
            audit_qs = audit_qs.filter(payload__forced=True)
        if audit_rev_tag:
            audit_qs = studio_admin.filter_studio_audit_by_revision_tag(
                audit_qs, m.subsystem, audit_rev_tag
            )
        ctx["studio_audit_log"] = list(audit_qs.select_related("user").order_by("-created_at")[:12])
        ctx["studio_audit_filter"] = audit_action
        ctx["studio_audit_forced_only"] = forced_only
        ctx["studio_audit_rev_tag"] = audit_rev_tag
        ctx["studio_audit_actions"] = STUDIO_AUDIT_ACTIONS
        export_action = audit_action or "studio."
        from urllib.parse import urlencode

        export_params = {"action": export_action}
        if forced_only:
            export_params["forced"] = "1"
        if audit_rev_tag:
            export_params["audit_rev_tag"] = audit_rev_tag
        ctx["studio_audit_export_filtered_url"] = (
            reverse("platform-studio-audit-export") + "?" + urlencode(export_params)
        )
        ctx["studio_stats"] = studio_admin.studio_summary(m.subsystem)
        rev_export_url = reverse("platform-studio-revisions-export")
        export_params = {}
        if rev_tag_filter:
            export_params["tag"] = rev_tag_filter
        if rev_q_filter:
            export_params["q"] = rev_q_filter
        if export_params:
            rev_export_url += "?" + urlencode(export_params)
        ctx["studio_revisions_export_url"] = rev_export_url
        ctx["studio_revisions_pinned_export_url"] = (
            reverse("platform-studio-revisions-export") + "?" + urlencode({"pinned": "1"})
        )
        ctx["studio_pinned_revision_ids"] = set(studio_admin.get_pinned_revision_ids(m.subsystem))
        from delayu.services.studio_activity import build_studio_activity_digest
        from delayu.services.studio_activity_schedule import get_activity_digest_schedule

        from delayu.services.studio_compliance_schedule import get_compliance_export_schedule

        ctx["studio_activity_digest"] = build_studio_activity_digest(m.subsystem, days=7, limit=8)
        ctx["studio_activity_digest_schedule"] = get_activity_digest_schedule(m.subsystem)
        ctx["studio_compliance_export_schedule"] = get_compliance_export_schedule(m.subsystem)
        checks = ctx.get("studio_health_checks") or studio_admin.subsystem_health_checks(m.subsystem)
        for check in checks:
            url_name = check.get("url_name")
            if url_name:
                try:
                    check["url"] = reverse(url_name)
                except Exception:
                    check["url"] = ""
        ctx["studio_health_checks"] = checks
        ctx["studio_forced_log"] = list(
            AuditLog.objects.filter(
                subsystem=m.subsystem,
                action__in=("studio.import", "studio.restore"),
            )
            .filter(payload__forced=True)
            .select_related("user")
            .order_by("-created_at")[:10]
        )
        from delayu.services.studio_publish_schedule import get_scheduled_publish

        sched = get_scheduled_publish(m.subsystem)
        if sched:
            sched = dict(sched)
            explicit = sched.get("tags") if isinstance(sched.get("tags"), list) else None
            sched["publish_tags_preview"] = studio_admin.preview_publish_tags(
                m.subsystem, explicit
            )["merged"]
        ctx["studio_scheduled_publish"] = sched
        ctx["studio_clone_targets"] = [
            {
                "code": row["subsystem__code"],
                "name": row["subsystem__name"],
            }
            for row in SubsystemMembership.objects.filter(user=self.request.user)
            .exclude(subsystem_id=m.subsystem_id)
            .order_by("subsystem__name")
            .values("subsystem__code", "subsystem__name")
        ]
        ctx["studio_revisions_json"] = json.dumps(
            [
                {
                    "id": r.pk,
                    "version": r.version_label,
                    "created_at": r.created_at.strftime("%d.%m.%Y %H:%M"),
                    "comment": r.comment or "",
                }
                for r in ctx["studio_revisions"]
            ],
            ensure_ascii=False,
        )
        return ctx


class StudioPreviewView(StudioMixin, TemplateView):
    studio_slug = "preview"
    template_name = "platform/studio/preview.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Просмотр как пользователь"
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        memberships = (
            SubsystemMembership.objects.filter(subsystem=m.subsystem)
            .select_related("user", "role", "organization")
            .order_by("user__username")
        )
        role_id = self.request.GET.get("role")
        user_id = self.request.GET.get("user")
        role = roles.filter(pk=role_id).first() if role_id else roles.first()
        membership = None
        if user_id:
            membership = memberships.filter(user_id=user_id).first()
        elif role:
            membership = memberships.filter(role=role).first()
        if not membership and memberships.exists():
            membership = memberships.first()
            role = membership.role
        include_draft = self.request.GET.get("draft") == "1"
        ctx["roles"] = roles
        ctx["memberships"] = memberships
        ctx["active_role"] = role
        ctx["active_membership"] = membership
        ctx["include_draft"] = include_draft
        if membership:
            preview = studio_admin.preview_as_membership(
                m.subsystem, membership, include_draft=include_draft
            )
            ctx["preview"] = preview
            ctx["preview_json"] = json.dumps(preview, ensure_ascii=False)
        elif role:
            preview = studio_admin.preview_as_role(
                m.subsystem, role, include_draft=include_draft
            )
            ctx["preview"] = preview
            ctx["preview_json"] = json.dumps(preview, ensure_ascii=False)
        return ctx


class StudioFormBuilderView(StudioMixin, TemplateView):
    module_code = "M74"
    studio_slug = "forms"
    template_name = "platform/studio/form_builder.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор форм"
        ctx["field_types"] = studio.FORM_FIELD_TYPES
        pk = self.kwargs.get("pk")
        if pk:
            schema = get_object_or_404(FormSchema, pk=pk, subsystem=m.subsystem)
        else:
            schema = FormSchema.objects.filter(subsystem=m.subsystem, target="case").first()
        ctx["schema"] = schema
        ctx["schema_json"] = json.dumps(schema.schema if schema else [], ensure_ascii=False)
        ctx["schemas"] = FormSchema.objects.filter(subsystem=m.subsystem).order_by("target", "code")
        ctx["nsi_classifiers"] = NSIClassifier.objects.filter(subsystem=m.subsystem, is_active=True)
        from delayu.models import RegistryType

        ctx["registries_json"] = json.dumps(
            [
                {"code": r.code, "name": r.name}
                for r in RegistryType.objects.filter(subsystem=m.subsystem, is_active=True).order_by(
                    "name"
                )
            ],
            ensure_ascii=False,
        )
        ctx["field_library_json"] = json.dumps(studio.FIELD_LIBRARY_BLOCKS, ensure_ascii=False)
        ctx["studio_form_diff_url"] = reverse("platform-studio-form-diff")
        ctx["studio_form_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        return ctx


class StudioBpmEditorView(StudioMixin, TemplateView):
    module_code = "M33"
    studio_slug = "bpm"
    template_name = "platform/studio/bpm_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "BPMN-редактор"
        ctx["node_types"] = studio.BPM_NODE_TYPES
        pk = self.kwargs.get("pk")
        tpl = None
        if pk:
            tpl = get_object_or_404(BPMTemplate, pk=pk, subsystem=m.subsystem)
        else:
            tpl = BPMTemplate.objects.filter(subsystem=m.subsystem).first()
        ctx["template"] = tpl
        diagram = tpl.diagram if tpl and tpl.diagram else {"nodes": [], "edges": []}
        ctx["diagram_json"] = json.dumps(diagram, ensure_ascii=False)
        ctx["templates"] = BPMTemplate.objects.filter(subsystem=m.subsystem).order_by("code")
        ctx["form_schemas_json"] = json.dumps(
            [
                {"code": s.code, "name": s.name or s.code}
                for s in FormSchema.objects.filter(subsystem=m.subsystem, is_active=True).order_by(
                    "target", "code"
                )
            ],
            ensure_ascii=False,
        )
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        ctx["roles_json"] = json.dumps(
            [{"code": r.code, "name": r.name} for r in roles], ensure_ascii=False
        )
        if tpl:
            from delayu.services.bpm_metrics import template_node_metrics

            ctx["node_metrics_json"] = json.dumps(
                template_node_metrics(tpl), ensure_ascii=False
            )
        else:
            ctx["node_metrics_json"] = "{}"
        ctx["studio_bpm_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_bpm_diff_url"] = reverse("platform-studio-bpm-diff")
        return ctx


class StudioMenuEditorView(StudioMixin, TemplateView):
    studio_slug = "menu"
    template_name = "platform/studio/menu_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор меню"
        layout = studio_admin.draft_value(m.subsystem, "menu")
        ctx["layout_json"] = json.dumps(studio.normalize_menu_layout(layout), ensure_ascii=False)
        ctx["menu_is_draft"] = "menu" in (m.subsystem.studio_draft or {})
        ctx["all_items"] = studio.flat_menu_items()
        ctx["all_items_json"] = json.dumps(ctx["all_items"], ensure_ascii=False)
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        ctx["roles_json"] = json.dumps(
            [{"code": r.code, "name": r.name} for r in roles], ensure_ascii=False
        )
        ctx["badge_options_json"] = json.dumps(studio.MENU_BADGE_OPTIONS, ensure_ascii=False)
        ctx["studio_menu_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_menu_diff_url"] = reverse("platform-studio-menu-diff")
        return ctx


class StudioDashboardEditorView(StudioMixin, TemplateView):
    module_code = "M85"
    studio_slug = "dashboard"
    template_name = "platform/studio/dashboard_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор дашборда"
        ctx["widget_catalog"] = studio.DASHBOARD_WIDGETS
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        role_id = self.request.GET.get("role")
        role = roles.filter(pk=role_id).first() if role_id else roles.first()
        ctx["roles"] = roles
        ctx["active_role"] = role
        widgets = []
        if role:
            raw = studio_admin.role_layout_widgets(
                m.subsystem, role, RoleStudioLayout.Kind.DASHBOARD
            )
            if raw:
                widgets = raw
        if not widgets:
            layout = UserDashboardLayout.objects.filter(
                user=self.request.user, subsystem=m.subsystem, is_default=True
            ).first()
            if layout and layout.widgets:
                widgets = layout.widgets
        if not widgets:
            widgets = [
                {"id": w["id"], "label": w["label"], "w": w["w"], "h": w["h"]}
                for w in studio.DASHBOARD_WIDGETS[:4]
            ]
        ctx["widgets_json"] = json.dumps(widgets, ensure_ascii=False)
        ctx["catalog_json"] = json.dumps(studio.DASHBOARD_WIDGETS, ensure_ascii=False)
        return ctx


class StudioTodayEditorView(StudioMixin, TemplateView):
    module_code = "M08"
    studio_slug = "today"
    template_name = "platform/studio/today_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор «Мне на сегодня»"
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        role_id = self.request.GET.get("role")
        role = roles.filter(pk=role_id).first() if role_id else roles.first()
        ctx["roles"] = roles
        ctx["active_role"] = role
        widgets = []
        if role:
            raw = studio_admin.role_layout_widgets(
                m.subsystem, role, RoleStudioLayout.Kind.TODAY
            )
            if raw:
                widgets = raw
        if not widgets:
            widgets = [w["id"] for w in studio.TODAY_WIDGETS]
        ctx["widgets"] = widgets
        ctx["today_catalog"] = studio.TODAY_WIDGETS
        return ctx


class StudioCorrespondenceEditorView(StudioMixin, TemplateView):
    module_code = "M27"
    studio_slug = "correspondence"
    template_name = "platform/studio/correspondence_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Маршрут корреспонденции"
        wf = studio_admin.draft_value(m.subsystem, "correspondence")
        ctx["workflow_json"] = json.dumps(wf, ensure_ascii=False)
        ctx["corr_is_draft"] = "correspondence" in (m.subsystem.studio_draft or {})
        ctx["step_catalog"] = studio.CORR_WORKFLOW_STEPS
        ctx["studio_corr_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_corr_diff_url"] = reverse("platform-studio-correspondence-diff")
        return ctx


class StudioPrintEditorView(StudioMixin, TemplateView):
    module_code = "M29"
    studio_slug = "print"
    template_name = "platform/studio/print_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "WYSIWYG печатных форм"
        ctx["variables"] = studio.PRINT_VARIABLES
        pk = self.kwargs.get("pk")
        tpl = None
        if pk:
            tpl = get_object_or_404(PrintTemplate, pk=pk, subsystem=m.subsystem)
        else:
            tpl = PrintTemplate.objects.filter(subsystem=m.subsystem).first()
        ctx["template"] = tpl
        ctx["templates"] = PrintTemplate.objects.filter(subsystem=m.subsystem).order_by("code")
        ctx["studio_print_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_print_diff_url"] = reverse("platform-studio-print-diff")
        return ctx


class StudioPermissionsEditorView(StudioMixin, TemplateView):
    module_code = "M02"
    studio_slug = "permissions"
    template_name = "platform/studio/permissions_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Матрица прав"
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        role_id = self.request.GET.get("role")
        role = roles.filter(pk=role_id).first() if role_id else roles.first()
        ctx["roles"] = roles
        ctx["active_role"] = role
        ctx["modules"] = list(enabled_modules_for_subsystem(m.subsystem))
        matrix = []
        if role:
            from delayu.models import RoleModulePermission
            from delayu.services.role_inheritance import effective_matrix_row

            perms = {
                p.module_id: p
                for p in RoleModulePermission.objects.filter(role=role).select_related("module")
            }
            for mod in ctx["modules"]:
                matrix.append(effective_matrix_row(role, mod, perms.get(mod.id)))
        ctx["matrix_json"] = json.dumps(matrix, ensure_ascii=False)
        ctx["parent_role_options"] = [
            r for r in roles if not role or r.pk != role.pk
        ]
        ctx["presets"] = studio.PERM_PRESETS
        return ctx


class StudioNsiEditorView(StudioMixin, TemplateView):
    module_code = "M73"
    studio_slug = "nsi"
    template_name = "platform/studio/nsi_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Редактор НСИ"
        pk = self.kwargs.get("pk")
        clf = None
        if pk:
            clf = get_object_or_404(NSIClassifier, pk=pk, subsystem=m.subsystem)
        else:
            clf = NSIClassifier.objects.filter(subsystem=m.subsystem).first()
        ctx["classifier"] = clf
        values = []
        if clf:
            values = list(
                clf.values.filter(is_active=True).order_by("sort_order", "name").values(
                    "id", "code", "name", "sort_order"
                )
            )
        ctx["values_json"] = json.dumps(values, ensure_ascii=False)
        ctx["classifiers"] = NSIClassifier.objects.filter(subsystem=m.subsystem).order_by("name")
        ctx["studio_nsi_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_nsi_diff_url"] = reverse("platform-studio-nsi-diff")
        return ctx


class StudioIntegrationEditorView(StudioMixin, TemplateView):
    module_code = "M42"
    studio_slug = "integration"
    template_name = "platform/studio/integration_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Pipeline интеграций"
        ctx["node_types"] = studio.INTEGRATION_PIPELINE_NODES
        pk = self.kwargs.get("pk")
        ep = None
        if pk:
            ep = get_object_or_404(IntegrationEndpoint, pk=pk, subsystem=m.subsystem)
        else:
            ep = IntegrationEndpoint.objects.filter(subsystem=m.subsystem).first()
        ctx["endpoint"] = ep
        pipeline = (ep.config or {}).get("pipeline") if ep else {"nodes": [], "edges": []}
        ctx["pipeline_json"] = json.dumps(pipeline or {"nodes": [], "edges": []}, ensure_ascii=False)
        ctx["endpoints"] = IntegrationEndpoint.objects.filter(subsystem=m.subsystem).order_by("code")
        ctx["studio_int_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_int_diff_url"] = reverse("platform-studio-integration-diff")
        return ctx


class StudioPoliciesEditorView(StudioMixin, TemplateView):
    module_code = "M78"
    studio_slug = "policies"
    template_name = "platform/studio/policies_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        from delayu.forms_exploitation import DataRetentionPolicyForm, SiemExportConfigForm
        from delayu.services.retention import get_or_create_retention_policy, retention_alerts, retention_expired
        from delayu.services.siem_export import get_or_create_siem_config

        ctx["page_title"] = "Политики хранения и SIEM"
        retention = get_or_create_retention_policy(m.subsystem)
        siem = get_or_create_siem_config(m.subsystem)
        ctx["retention_form"] = DataRetentionPolicyForm(instance=retention)
        ctx["siem_form"] = SiemExportConfigForm(instance=siem)
        ctx["retention_alerts"] = retention_alerts(m.subsystem)
        ctx["retention_expired_count"] = retention_expired(m.subsystem)
        ctx["studio_policy_revisions"] = StudioConfigRevision.objects.filter(
            subsystem=m.subsystem
        ).order_by("-created_at")[:12]
        ctx["studio_policies_diff_url"] = reverse("platform-studio-policies-diff")
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        from delayu.forms_exploitation import DataRetentionPolicyForm, SiemExportConfigForm
        from delayu.services.retention import get_or_create_retention_policy
        from delayu.services.siem_export import get_or_create_siem_config

        retention = get_or_create_retention_policy(m.subsystem)
        siem = get_or_create_siem_config(m.subsystem)
        kind = request.POST.get("form_kind", "retention")
        if kind == "siem":
            form = SiemExportConfigForm(request.POST, instance=siem)
            if form.is_valid():
                form.save()
                audit.log_action(
                    request.user,
                    m.subsystem,
                    "studio.policies.siem",
                    "SiemExportConfig",
                    siem.pk,
                    request=request,
                )
                messages.success(request, "Настройки SIEM сохранены.")
            else:
                messages.error(request, "Проверьте URL webhook.")
        else:
            form = DataRetentionPolicyForm(request.POST, instance=retention)
            if form.is_valid():
                form.save()
                audit.log_action(
                    request.user,
                    m.subsystem,
                    "studio.policies.retention",
                    "DataRetentionPolicy",
                    retention.pk,
                    request=request,
                )
                messages.success(request, "Политика хранения сохранена.")
            else:
                messages.error(request, "Проверьте поля политики хранения.")
        return redirect("platform-studio-policies")


class StudioCabinetEditorView(StudioMixin, TemplateView):
    module_code = "M07"
    studio_slug = "cabinet"
    template_name = "platform/studio/cabinet_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Раскладка личного кабинета"
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        prefs = profile.theme_prefs or {}
        widgets = prefs.get("cabinet_widgets") or [w["id"] for w in studio.CABINET_WIDGETS]
        ctx["widget_catalog"] = studio.CABINET_WIDGETS
        ctx["widgets_json"] = json.dumps(widgets, ensure_ascii=False)
        ctx["catalog_json"] = json.dumps(studio.CABINET_WIDGETS, ensure_ascii=False)
        return ctx


class StudioSaveApiView(StudioMixin, View):
    """Универсальное API сохранения конструкторов."""

    def post(self, request, editor):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        if editor == "forms":
            if not user_can(request.user, "M74", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            schema_id = payload.get("schema_id")
            schema = get_object_or_404(FormSchema, pk=schema_id, subsystem=m.subsystem)
            schema.schema = payload.get("schema") or []
            schema.save(update_fields=["schema", "updated_at"])
            sync_registry_form_schema(schema)
        elif editor == "bpm":
            if not user_can(request.user, "M33", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            tpl = get_object_or_404(BPMTemplate, pk=payload["template_id"], subsystem=m.subsystem)
            diagram = payload.get("diagram") or {}
            tpl.diagram = diagram
            tpl.steps = studio.diagram_to_bpm_steps(diagram)
            tpl.save(update_fields=["diagram", "steps"])
        elif editor == "menu":
            layout = studio.normalize_menu_layout(payload.get("layout") or [])
            studio_admin.save_draft(m.subsystem, "menu", layout)
        elif editor == "dashboard":
            widgets = payload.get("widgets") or []
            role_id = payload.get("role_id")
            if role_id:
                role = get_object_or_404(Role, pk=role_id, subsystem=m.subsystem)
                studio_admin.save_role_layout(
                    m.subsystem, role, RoleStudioLayout.Kind.DASHBOARD, widgets
                )
            else:
                layout, _ = UserDashboardLayout.objects.get_or_create(
                    user=request.user,
                    subsystem=m.subsystem,
                    name="Студия",
                    defaults={"is_default": True, "widgets": widgets},
                )
                layout.widgets = widgets
                layout.is_default = True
                layout.save(update_fields=["widgets", "is_default", "updated_at"])
        elif editor == "today":
            if not user_can(request.user, "M08", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            widgets = payload.get("widgets") or []
            role_id = payload.get("role_id")
            if not role_id:
                return JsonResponse({"ok": False, "error": "role_id required"}, status=400)
            role = get_object_or_404(Role, pk=role_id, subsystem=m.subsystem)
            studio_admin.save_role_layout(
                m.subsystem, role, RoleStudioLayout.Kind.TODAY, widgets
            )
        elif editor == "correspondence":
            studio_admin.save_draft(
                m.subsystem, "correspondence", payload.get("workflow") or {}
            )
        elif editor == "print":
            if not user_can(request.user, "M29", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            tpl = get_object_or_404(PrintTemplate, pk=payload["template_id"], subsystem=m.subsystem)
            tpl.body = payload.get("body") or ""
            tpl.save(update_fields=["body"])
        elif editor == "permissions":
            if not user_can(request.user, "M02", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            role = get_object_or_404(Role, pk=payload["role_id"], subsystem=m.subsystem)
            parent_id = payload.get("parent_role_id")
            if parent_id:
                parent = get_object_or_404(Role, pk=parent_id, subsystem=m.subsystem)
                if parent.pk == role.pk:
                    return JsonResponse({"ok": False, "error": "self_parent"}, status=400)
                role.parent_role = parent
            else:
                role.parent_role = None
            role.save(update_fields=["parent_role"])
            from delayu.models import ModuleCatalog, RoleModulePermission

            modules = {mod.code: mod for mod in enabled_modules_for_subsystem(m.subsystem)}
            for row in payload.get("matrix") or []:
                mod = modules.get(row.get("code"))
                if not mod:
                    continue
                own = row.get("own") or row
                if not any(
                    own.get(a)
                    for a in (
                        "view",
                        "create",
                        "change",
                        "delete",
                        "view_pii",
                        "export_pii",
                        "approve",
                        "sign",
                        "archive",
                        "bulk",
                    )
                ):
                    RoleModulePermission.objects.filter(role=role, module=mod).delete()
                    continue
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults={
                        "can_view": own.get("view", False),
                        "can_create": own.get("create", False),
                        "can_change": own.get("change", False),
                        "can_delete": own.get("delete", False),
                        "can_view_pii": own.get("view_pii", False),
                        "can_export_pii": own.get("export_pii", False),
                        "can_approve": own.get("approve", False),
                        "can_sign": own.get("sign", False),
                        "can_archive": own.get("archive", False),
                        "can_bulk": own.get("bulk", False),
                    },
                )
        elif editor == "nsi":
            if not user_can(request.user, "M73", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            clf = get_object_or_404(NSIClassifier, pk=payload["classifier_id"], subsystem=m.subsystem)
            for idx, row in enumerate(payload.get("values") or [], start=1):
                NSIValue.objects.filter(pk=row["id"], classifier=clf).update(
                    sort_order=idx, name=row.get("name", ""), code=row.get("code", "")
                )
        elif editor == "integration":
            if not user_can(request.user, "M42", "change"):
                return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
            ep = get_object_or_404(IntegrationEndpoint, pk=payload["endpoint_id"], subsystem=m.subsystem)
            cfg = dict(ep.config or {})
            cfg["pipeline"] = payload.get("pipeline") or {}
            smev_cfg = payload.get("smev_config")
            if isinstance(smev_cfg, dict) and ep.endpoint_type == IntegrationEndpoint.EndpointType.SMEV:
                for key in (
                    "transport",
                    "url",
                    "test_mode",
                    "client_id",
                    "smev_version",
                    "http_timeout",
                ):
                    if key in smev_cfg:
                        cfg[key] = smev_cfg[key]
            ep.config = cfg
            ep.save(update_fields=["config"])
        elif editor == "cabinet":
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            prefs = dict(profile.theme_prefs or {})
            prefs["cabinet_widgets"] = payload.get("widgets") or []
            profile.theme_prefs = prefs
            profile.save(update_fields=["theme_prefs", "updated_at"])
        else:
            return JsonResponse({"ok": False, "error": "unknown editor"}, status=400)

        m.subsystem.refresh_from_db()
        audit.log_action(
            request.user,
            m.subsystem,
            f"studio.save.{editor}",
            "Studio",
            editor,
            payload={"keys": list(payload.keys())},
            request=request,
        )
        draft_editors = {"menu", "correspondence"}
        return JsonResponse(
            {
                "ok": True,
                "draft": editor in draft_editors,
                "has_draft": m.subsystem.studio_has_draft,
            }
        )


class StudioPublishApiView(StudioMixin, View):
    """Публикация черновика меню/СЭД и создание ревизии."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        if not m.subsystem.studio_has_draft:
            revision = StudioConfigRevision.objects.create(
                subsystem=m.subsystem,
                version_label=studio_admin.next_version_label(m.subsystem),
                snapshot=studio_admin.capture_snapshot(m.subsystem),
                comment=(payload.get("comment") or "Снимок без черновика").strip()[:255],
                published_by=request.user,
            )
            m.subsystem.config_version = revision.version_label
            m.subsystem.published_at = revision.created_at
            m.subsystem.save(update_fields=["config_version", "published_at", "updated_at"])
            from delayu.services.studio_publish_events import on_studio_config_published

            on_studio_config_published(
                m.subsystem,
                revision,
                request.user,
                comment=payload.get("comment") or "Снимок без черновика",
                source="snapshot",
            )
            publish_tags = payload.get("tags") if "tags" in payload else None
            final_tags = studio_admin.merge_publish_tags(m.subsystem, publish_tags)
            if final_tags:
                studio_admin.set_revision_tags(m.subsystem, revision.pk, final_tags)
            studio_admin.clear_pending_publish_tags(m.subsystem)
        else:
            revision = studio_admin.publish_studio_draft(
                m.subsystem,
                request.user,
                comment=payload.get("comment") or "",
                tags=payload.get("tags") if "tags" in payload else None,
            )

        tag_list = studio_admin.get_revision_tags_map(m.subsystem).get(revision.pk, [])

        m.subsystem.refresh_from_db()
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.publish",
            "StudioConfigRevision",
            revision.pk,
            payload={"version": revision.version_label},
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "version": revision.version_label,
                "has_draft": m.subsystem.studio_has_draft,
                "tags": tag_list,
            }
        )


class StudioPublishDryRunApiView(StudioMixin, View):
    """Предпросмотр diff черновик vs опубликованное перед публикацией."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        tags = payload.get("tags")
        if tags is not None and not isinstance(tags, list):
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags = []
        try:
            result = studio_admin.dry_run_publish(m.subsystem, tags=tags)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        if result.get("ok"):
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.dry_run.publish",
                "Subsystem",
                m.subsystem.pk,
                payload={
                    "draft_sections": result.get("draft_sections"),
                    "changed_sections": (result.get("diff") or {}).get("changed_sections"),
                    "next_version": result.get("next_version"),
                    "publish_tags": result.get("publish_tags"),
                },
                request=request,
            )
        return JsonResponse(result)


class StudioAuditExportView(StudioMixin, View):
    """CSV журнала действий Студии (studio.*)."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_studio_audit_csv

        mask = request.GET.get("mask_pii") == "1"
        action = request.GET.get("action", "studio.").strip() or "studio."
        forced_only = request.GET.get("forced") == "1"
        revision_tag = request.GET.get("audit_rev_tag", "").strip()
        return export_studio_audit_csv(
            m.subsystem,
            action=action,
            mask_pii=mask,
            forced_only=forced_only,
            revision_tag=revision_tag,
        )


class StudioForcedAuditExportView(StudioMixin, View):
    """CSV журнала принудительных импортов и откатов."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_studio_forced_audit_csv

        mask = request.GET.get("mask_pii") == "1"
        return export_studio_forced_audit_csv(m.subsystem, mask_pii=mask)


class StudioComplianceExportView(StudioMixin, View):
    """ZIP compliance-пакет: конфигурация + журнал studio.*."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_studio_compliance_package
        from delayu.services.studio_publish_events import on_studio_compliance_exported

        mask = request.GET.get("mask_pii") == "1"
        revision_tag = request.GET.get("tag", "").strip()
        resp = export_studio_compliance_package(
            m.subsystem, mask_pii=mask, revision_tag=revision_tag
        )
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        filename = f"studio-compliance-{m.subsystem.code}-{stamp}.zip"
        on_studio_compliance_exported(
            m.subsystem,
            request.user,
            filename=filename,
            size=len(resp.content),
            source="manual",
            mask_pii=mask,
            revision_tag=revision_tag,
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.compliance_export",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "filename": filename,
                "size": len(resp.content),
                "mask_pii": mask,
                "revision_tag": revision_tag or None,
            },
            request=request,
        )
        return resp


class StudioDiscardDraftApiView(StudioMixin, View):
    def post(self, request):
        m = _ctx_membership(self)
        studio_admin.discard_studio_draft(m.subsystem)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.discard_draft",
            "Subsystem",
            m.subsystem.pk,
            request=request,
        )
        return JsonResponse({"ok": True, "has_draft": False})


class StudioBpmSimulateApiView(StudioMixin, View):
    module_code = "M33"

    def post(self, request):
        from delayu.services.bpm_simulator import simulate_diagram

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        diagram = payload.get("diagram") or {}
        result = simulate_diagram(diagram, hours_per_task=int(payload.get("hours_per_task") or 8))
        return JsonResponse(result)


class StudioBpmMetricsApiView(StudioMixin, View):
    module_code = "M33"

    def get(self, request):
        from delayu.services.bpm_metrics import template_node_metrics

        m = _ctx_membership(self)
        tpl_id = request.GET.get("template_id")
        if not tpl_id:
            return JsonResponse({"ok": False, "error": "template_id required"}, status=400)
        tpl = get_object_or_404(BPMTemplate, pk=tpl_id, subsystem=m.subsystem)
        return JsonResponse({"ok": True, "metrics": template_node_metrics(tpl)})


class StudioExportConfigView(StudioMixin, View):
    def get(self, request):
        m = _ctx_membership(self)
        package = studio_admin.export_config_package(m.subsystem)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.export",
            "Subsystem",
            m.subsystem.pk,
            request=request,
        )
        body = json.dumps(package, ensure_ascii=False, indent=2)
        filename = f"delayu-{m.subsystem.code}-config.json"
        resp = HttpResponse(body, content_type="application/json; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


class StudioImportConfigApiView(StudioMixin, View):
    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_package_validate import validate_config_package

        validation = validate_config_package(payload)
        if not validation["ok"]:
            return JsonResponse(
                {
                    "ok": False,
                    "error": "; ".join(validation["errors"]),
                    "validation": validation,
                },
                status=400,
            )
        from delayu.services.studio_import_risk import ImportRiskError

        to_draft = payload.get("to_draft", True) is not False
        force = payload.get("force") is True
        try:
            stats = studio_admin.import_config_package(
                m.subsystem, payload, to_draft=to_draft, force=force
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        except ImportRiskError as exc:
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    "blocked": True,
                    "risk": exc.risk,
                },
                status=409,
            )
        if force and stats.get("import_risk", {}).get("blocked"):
            from delayu.services.studio_forced_import import notify_studio_forced_import

            notify_studio_forced_import(
                m.subsystem, request.user, stats["import_risk"], action="import"
            )
        m.subsystem.refresh_from_db()
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.import",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "stats": stats,
                "warnings": validation.get("warnings") or [],
                "forced": force and bool(stats.get("import_risk", {}).get("blocked")),
            },
            request=request,
        )
        return JsonResponse(
            {
                "ok": True,
                "stats": stats,
                "has_draft": m.subsystem.studio_has_draft,
                "validation": validation,
            }
        )


class StudioPackageValidateApiView(StudioMixin, View):
    """Валидация пакета конфигурации без импорта."""

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_package_validate import validate_config_package

        result = validate_config_package(payload)
        return JsonResponse(result)


class StudioBlueprintValidateApiView(StudioMixin, View):
    """Валидация JSON шаблона delayu-blueprint без применения."""

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_package_validate import validate_blueprint_package

        result = validate_blueprint_package(payload)
        return JsonResponse(result)


class StudioIntegrationDryRunApiView(StudioMixin, View):
    module_code = "M42"

    def post(self, request):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_integration import dry_run_pipeline

        result = dry_run_pipeline(
            payload.get("pipeline") or {},
            sample=payload.get("sample"),
        )
        return JsonResponse(result)


class StudioIntegrationRunApiView(StudioMixin, View):
    """Runtime-прогон pipeline (СМЭВ через очередь интеграций)."""

    module_code = "M42"

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_integration import run_pipeline

        endpoint = None
        ep_id = payload.get("endpoint_id")
        if ep_id:
            endpoint = IntegrationEndpoint.objects.filter(
                pk=int(ep_id), subsystem=m.subsystem
            ).first()
        result = run_pipeline(
            payload.get("pipeline") or {},
            sample=payload.get("sample"),
            mode=payload.get("mode") or "runtime",
            endpoint=endpoint,
        )
        if result.get("ok"):
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.integration.runtime",
                "IntegrationEndpoint",
                endpoint.pk if endpoint else "",
                payload={"mode": result.get("mode")},
                request=request,
            )
        return JsonResponse(result)


class StudioSetupWizardView(StudioMixin, TemplateView):
    studio_slug = "setup"
    template_name = "platform/studio/setup_wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        from delayu.services.studio_setup import setup_progress

        ctx["page_title"] = "Первичная настройка"
        ctx["breadcrumbs"] = [
            {"label": "Студия ДелаЮ", "url": reverse("platform-studio")},
            {"label": "Первичная настройка", "url": None},
        ]
        ctx["studio_setup"] = setup_progress(m.subsystem)
        ctx["studio_setup_api_url"] = reverse("platform-studio-setup-api")
        ctx["studio_blueprints"] = studio.STUDIO_BLUEPRINTS
        return ctx


class StudioSetupApiView(StudioMixin, View):
    """Действия мастера первичной настройки."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

        action = payload.get("action", "")
        from delayu.services import studio_setup

        if action == "dismiss":
            studio_setup.dismiss_setup_wizard(m.subsystem)
            return JsonResponse({"ok": True, **studio_setup.setup_progress(m.subsystem)})

        if action == "mark":
            step_id = payload.get("step_id", "")
            if not step_id:
                return JsonResponse({"ok": False, "error": "step_id required"}, status=400)
            return JsonResponse(
                {"ok": True, **studio_setup.mark_setup_step(m.subsystem, step_id)}
            )

        if action == "blueprint":
            blueprint_id = payload.get("blueprint_id") or "operator_daily"
            try:
                result = studio_admin.apply_blueprint(m.subsystem, blueprint_id)
            except ValueError:
                return JsonResponse({"ok": False, "error": "unknown blueprint"}, status=400)
            studio_setup.mark_setup_step(m.subsystem, "blueprint")
            m.subsystem.refresh_from_db()
            return JsonResponse(
                {
                    "ok": True,
                    "result": result,
                    **studio_setup.setup_progress(m.subsystem),
                }
            )

        if action == "publish":
            if not m.subsystem.studio_has_draft:
                return JsonResponse({"ok": False, "error": "Нет черновика для публикации"}, status=400)
            rev = studio_admin.publish_studio_draft(
                m.subsystem, request.user, comment="Мастер первичной настройки"
            )
            studio_setup.mark_setup_step(m.subsystem, "publish")
            return JsonResponse(
                {
                    "ok": True,
                    "version": rev.version_label,
                    **studio_setup.setup_progress(m.subsystem),
                }
            )

        if action == "smev_stub":
            ep = studio_setup.ensure_smev_stub_endpoint(m.subsystem)
            studio_setup.mark_setup_step(m.subsystem, "integrations")
            return JsonResponse(
                {
                    "ok": True,
                    "endpoint_id": ep.pk,
                    "code": ep.code,
                    **studio_setup.setup_progress(m.subsystem),
                }
            )

        return JsonResponse({"ok": False, "error": "unknown action"}, status=400)


class StudioRevisionCompareApiView(StudioMixin, View):
    """Сравнение двух ревизий или ревизии с текущим снимком."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_revision_compare import compare_snapshots_detailed

        rev_a = request.GET.get("a", "").strip()
        rev_b = request.GET.get("b", "").strip()
        if not rev_a or not rev_b:
            return JsonResponse({"ok": False, "error": "a and b required"}, status=400)

        def load_snapshot(token: str) -> dict:
            if token == "live":
                return studio_admin.capture_snapshot(m.subsystem)
            if token == "draft":
                return studio_admin.effective_snapshot(m.subsystem, include_draft=True)
            rev = get_object_or_404(
                StudioConfigRevision, pk=int(token), subsystem=m.subsystem
            )
            return rev.snapshot or {}

        try:
            before = load_snapshot(rev_a)
            after = load_snapshot(rev_b)
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid id"}, status=400)
        result = compare_snapshots_detailed(before, after)
        result["a"] = rev_a
        result["b"] = rev_b
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.compare_revisions",
            "StudioConfigRevision",
            "",
            payload={
                "a": rev_a,
                "b": rev_b,
                "changed_sections": result.get("changed_sections"),
                "has_detail_changes": result.get("has_detail_changes"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioSummaryApiView(StudioMixin, View):
    """JSON-сводка состояния Студии."""

    def get(self, request):
        m = _ctx_membership(self)
        return JsonResponse(studio_admin.studio_summary(m.subsystem))


class StudioRevisionExportView(StudioMixin, View):
    """Экспорт JSON одной ревизии."""

    def get(self, request, revision_id: int):
        m = _ctx_membership(self)
        rev = get_object_or_404(
            StudioConfigRevision, pk=int(revision_id), subsystem=m.subsystem
        )
        package = studio_admin.export_revision_package(rev)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.export_revision",
            "StudioConfigRevision",
            rev.pk,
            payload={"version": rev.version_label},
            request=request,
        )
        body = json.dumps(package, ensure_ascii=False, indent=2)
        filename = f"delayu-{m.subsystem.code}-rev-{rev.version_label}.json"
        resp = HttpResponse(body, content_type="application/json; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


class StudioRevisionCompareExportView(StudioMixin, View):
    """CSV детального сравнения двух ревизий."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_revision_compare_csv
        from delayu.services.studio_revision_compare import compare_snapshots_detailed

        rev_a = request.GET.get("a", "").strip()
        rev_b = request.GET.get("b", "").strip()
        if not rev_a or not rev_b:
            return JsonResponse({"ok": False, "error": "a and b required"}, status=400)

        def load_snapshot(token: str) -> dict:
            if token == "live":
                return studio_admin.capture_snapshot(m.subsystem)
            if token == "draft":
                return studio_admin.effective_snapshot(m.subsystem, include_draft=True)
            rev = get_object_or_404(
                StudioConfigRevision, pk=int(token), subsystem=m.subsystem
            )
            return rev.snapshot or {}

        try:
            before = load_snapshot(rev_a)
            after = load_snapshot(rev_b)
        except ValueError:
            return JsonResponse({"ok": False, "error": "invalid id"}, status=400)
        result = compare_snapshots_detailed(before, after)
        return export_revision_compare_csv(
            m.subsystem, result, rev_a=rev_a, rev_b=rev_b
        )


class StudioActivityDigestView(StudioMixin, View):
    """JSON-сводка активности Студии за период."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_activity import build_studio_activity_digest

        days = int(request.GET.get("days") or 7)
        limit = int(request.GET.get("limit") or 30)
        return JsonResponse(build_studio_activity_digest(m.subsystem, days=days, limit=limit))


class StudioActivityExportView(StudioMixin, View):
    """CSV активности Студии."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_studio_activity_digest_csv

        days = int(request.GET.get("days") or 7)
        return export_studio_activity_digest_csv(m.subsystem, days=days)


class StudioActivityNotifyView(StudioMixin, View):
    """Отправить сводку активности администраторам подсистемы."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            payload = {}
        days = int(payload.get("days") or request.GET.get("days") or 7)
        from delayu.services.studio_activity import notify_studio_activity_digest_admins

        count = notify_studio_activity_digest_admins(m.subsystem, days=days)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.activity_digest",
            "Subsystem",
            m.subsystem.pk,
            payload={"days": days, "notified": count},
            request=request,
        )
        return JsonResponse({"ok": True, "notified": count, "days": days})


class StudioActivityScheduleApiView(StudioMixin, View):
    """Расписание автоматической рассылки сводки активности."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_activity_schedule import get_activity_digest_schedule

        sched = get_activity_digest_schedule(m.subsystem)
        return JsonResponse({"ok": True, "schedule": sched or {}})

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_activity_schedule import set_activity_digest_schedule

        sched = set_activity_digest_schedule(
            m.subsystem,
            enabled=payload.get("enabled", True),
            interval_days=int(payload.get("interval_days") or 7),
            digest_days=int(payload.get("digest_days") or 7),
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.activity_digest_schedule",
            "Subsystem",
            m.subsystem.pk,
            payload=sched,
            request=request,
        )
        return JsonResponse({"ok": True, "schedule": sched})


class StudioRevisionsListApiView(StudioMixin, View):
    """JSON-список ревизий (закреплённые первыми)."""

    def get(self, request):
        m = _ctx_membership(self)
        limit = int(request.GET.get("limit") or 20)
        offset = int(request.GET.get("offset") or 0)
        tag = request.GET.get("tag", "").strip()
        q = request.GET.get("q", "").strip()
        return JsonResponse(
            studio_admin.list_studio_revisions(
                m.subsystem, limit=limit, offset=offset, tag=tag, q=q
            )
        )


class StudioRevisionTagsApiView(StudioMixin, View):
    """Список уникальных тегов ревизий."""

    def get(self, request):
        m = _ctx_membership(self)
        return JsonResponse(
            {"ok": True, "tags": studio_admin.list_revision_tags(m.subsystem)}
        )


class StudioRevisionsBulkExportView(StudioMixin, View):
    """ZIP-архив всех ревизий."""

    def get(self, request):
        m = _ctx_membership(self)
        max_revisions = int(request.GET.get("max") or 500)
        tag = request.GET.get("tag", "").strip()
        q = request.GET.get("q", "").strip()
        pinned_only = request.GET.get("pinned") == "1"
        resp = studio_admin.export_revisions_archive(
            m.subsystem,
            max_revisions=max_revisions,
            tag=tag,
            pinned_only=pinned_only,
            q=q,
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.export_revisions",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "max": max_revisions,
                "tag": tag or "",
                "q": q or "",
                "pinned_only": pinned_only,
            },
            request=request,
        )
        return resp


class StudioBlueprintCompareApiView(StudioMixin, View):
    """Сравнение шаблона конфигурации с ревизией."""

    def get(self, request):
        m = _ctx_membership(self)
        blueprint_id = request.GET.get("blueprint_id", "").strip()
        rev_id = request.GET.get("revision_id", "").strip()
        if not blueprint_id or not rev_id:
            return JsonResponse(
                {"ok": False, "error": "blueprint_id and revision_id required"},
                status=400,
            )
        try:
            result = studio_admin.compare_blueprint_with_revision(
                m.subsystem, blueprint_id, int(rev_id)
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.blueprint_compare",
            "StudioConfigRevision",
            rev_id,
            payload={"blueprint": blueprint_id, "revision_id": rev_id},
            request=request,
        )
        return JsonResponse(result)


class StudioBlueprintCompareLiveApiView(StudioMixin, View):
    """Сравнение шаблона с текущей опубликованной конфигурацией."""

    def get(self, request):
        m = _ctx_membership(self)
        blueprint_id = request.GET.get("blueprint_id", "").strip()
        if not blueprint_id:
            return JsonResponse({"ok": False, "error": "blueprint_id required"}, status=400)
        try:
            result = studio_admin.compare_blueprint_with_live(m.subsystem, blueprint_id)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.blueprint_compare_live",
            "Subsystem",
            m.subsystem.pk,
            payload={"blueprint": blueprint_id},
            request=request,
        )
        return JsonResponse(result)


class StudioBlueprintPackageCompareApiView(StudioMixin, View):
    """Сравнение JSON-шаблона с ревизией."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        rev_id = payload.get("revision_id")
        package = payload.get("package") or payload
        if not rev_id:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        try:
            result = studio_admin.compare_blueprint_package_with_revision(
                m.subsystem, package, int(rev_id)
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.blueprint_package_compare",
            "StudioConfigRevision",
            rev_id,
            payload={"revision_id": rev_id},
            request=request,
        )
        return JsonResponse(result)


class StudioBlueprintPackageCompareLiveApiView(StudioMixin, View):
    """Сравнение JSON-шаблона с текущей конфигурацией."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        package = payload.get("package") or payload
        try:
            result = studio_admin.compare_blueprint_package_with_live(m.subsystem, package)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.blueprint_package_compare_live",
            "Subsystem",
            m.subsystem.pk,
            payload={"blueprint": result.get("blueprint") or "custom"},
            request=request,
        )
        return JsonResponse(result)


class StudioRevisionPruneApiView(StudioMixin, View):
    """Очистка старых ревизий (с сохранением закреплённых)."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        keep = int(payload.get("keep") or 50)
        dry_run = payload.get("dry_run") is True
        result = studio_admin.prune_studio_revisions(m.subsystem, keep=keep, dry_run=dry_run)
        if result.get("ok") and not dry_run:
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.prune_revisions",
                "Subsystem",
                m.subsystem.pk,
                payload={
                    "keep": keep,
                    "deleted": result.get("deleted"),
                    "remaining": result.get("remaining"),
                },
                request=request,
            )
            from delayu.services.studio_publish_events import on_studio_revisions_pruned

            on_studio_revisions_pruned(
                m.subsystem,
                request.user,
                keep=keep,
                deleted=result.get("deleted") or 0,
                remaining=result.get("remaining") or 0,
            )
        return JsonResponse(result)


class StudioRevisionPinApiView(StudioMixin, View):
    """Закрепить / открепить ревизию (не удаляется при prune)."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        rev_id = payload.get("revision_id")
        if not rev_id:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        rev = get_object_or_404(StudioConfigRevision, pk=int(rev_id), subsystem=m.subsystem)
        pinned = payload.get("pinned", True) is not False
        ids = studio_admin.set_revision_pinned(m.subsystem, rev.pk, pinned=pinned)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.pin_revision",
            "StudioConfigRevision",
            rev.pk,
            payload={"version": rev.version_label, "pinned": pinned},
            request=request,
        )
        return JsonResponse({"ok": True, "pinned": pinned, "pinned_ids": ids})


class StudioRevisionMetaApiView(StudioMixin, View):
    """Комментарий и теги ревизии."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        rev_id = payload.get("revision_id")
        if not rev_id:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        tags = payload.get("tags")
        if tags is not None and not isinstance(tags, list):
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags = []
        try:
            result = studio_admin.update_revision_meta(
                m.subsystem,
                int(rev_id),
                comment=payload.get("comment") if "comment" in payload else None,
                tags=tags if "tags" in payload else None,
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        rev = get_object_or_404(StudioConfigRevision, pk=int(rev_id), subsystem=m.subsystem)
        from delayu.services.studio_publish_events import on_studio_revision_meta_updated

        on_studio_revision_meta_updated(
            m.subsystem,
            request.user,
            rev,
            comment=result.get("comment") or "",
            tags=result.get("tags") or [],
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.revision_meta",
            "StudioConfigRevision",
            rev_id,
            payload={
                "comment": result.get("comment"),
                "tags": result.get("tags"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioDefaultPublishTagsApiView(StudioMixin, View):
    """Теги по умолчанию при публикации."""

    def get(self, request):
        m = _ctx_membership(self)
        return JsonResponse(
            {
                "ok": True,
                "tags": studio_admin.get_default_publish_tags(m.subsystem),
                "pending": studio_admin.get_pending_publish_tags(m.subsystem),
            }
        )

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        tags = payload.get("tags")
        if tags is not None and not isinstance(tags, list):
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags = []
        saved = studio_admin.set_default_publish_tags(m.subsystem, tags or [])
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.default_publish_tags",
            "Subsystem",
            m.subsystem.pk,
            payload={"tags": saved},
            request=request,
        )
        return JsonResponse({"ok": True, "tags": saved})


class StudioClearPendingPublishTagsApiView(StudioMixin, View):
    """Сброс pending-тегов (после шаблона), без публикации."""

    def post(self, request):
        m = _ctx_membership(self)
        cleared = studio_admin.get_pending_publish_tags(m.subsystem)
        studio_admin.clear_pending_publish_tags(m.subsystem)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.pending_publish_tags_clear",
            "Subsystem",
            m.subsystem.pk,
            payload={"cleared": cleared},
            request=request,
        )
        return JsonResponse({"ok": True, "cleared": cleared, "pending": []})


class StudioRevisionBulkTagsApiView(StudioMixin, View):
    """Массовое изменение тегов ревизий."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        tags = payload.get("tags")
        if tags is not None and not isinstance(tags, list):
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            else:
                tags = []
        result = studio_admin.bulk_set_revision_tags(
            m.subsystem,
            payload.get("revision_ids") or [],
            tags or [],
            mode=(payload.get("mode") or "set"),
        )
        if result.get("count"):
            from delayu.services.studio_publish_events import on_studio_revision_tags_bulk

            on_studio_revision_tags_bulk(
                m.subsystem,
                request.user,
                revision_ids=result.get("updated") or [],
                mode=result.get("mode") or "set",
                tags=result.get("tags") or [],
                count=result.get("count") or 0,
            )
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.revision_tags_bulk",
                "Subsystem",
                m.subsystem.pk,
                payload={
                    "mode": result.get("mode"),
                    "tags": result.get("tags"),
                    "count": result.get("count"),
                },
                request=request,
            )
        return JsonResponse(result)


class StudioComplianceScheduleApiView(StudioMixin, View):
    """Расписание автоматического compliance export."""

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_compliance_schedule import get_compliance_export_schedule

        sched = get_compliance_export_schedule(m.subsystem)
        return JsonResponse({"ok": True, "schedule": sched or {}})

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        from delayu.services.studio_compliance_schedule import set_compliance_export_schedule

        sched = set_compliance_export_schedule(
            m.subsystem,
            enabled=payload.get("enabled", True),
            interval_days=int(payload.get("interval_days") or 30),
            mask_pii=payload.get("mask_pii") is True,
            revision_tag=(payload.get("revision_tag") or "").strip(),
        )
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.compliance_export_schedule",
            "Subsystem",
            m.subsystem.pk,
            payload=sched,
            request=request,
        )
        return JsonResponse({"ok": True, "schedule": sched})


class StudioSchedulePublishDryRunApiView(StudioMixin, View):
    """Dry-run перед отложенной публикацией."""

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_publish_schedule import preview_schedule_publish
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as tz

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        at_raw = (payload.get("at") or "").strip()
        at = parse_datetime(at_raw)
        if at is None:
            return JsonResponse({"ok": False, "error": "Некорректная дата"}, status=400)
        if tz.is_naive(at):
            at = tz.make_aware(at, tz.get_current_timezone())
        schedule_tags = payload.get("tags")
        if schedule_tags is not None and not isinstance(schedule_tags, list):
            if isinstance(schedule_tags, str):
                schedule_tags = [t.strip() for t in schedule_tags.split(",") if t.strip()]
            else:
                schedule_tags = []
        try:
            result = preview_schedule_publish(
                m.subsystem,
                at,
                comment=payload.get("comment") or "",
                tags=schedule_tags,
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.dry_run.schedule",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "at": at_raw,
                "changed_sections": (result.get("diff") or {}).get("changed_sections"),
                "publish_tags": result.get("publish_tags"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioRestoreRevisionApiView(StudioMixin, View):
    """Откат конфигурации к выбранной ревизии."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        rev_id = payload.get("revision_id")
        mode = payload.get("mode", "draft")
        if not rev_id:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        if mode not in ("draft", "apply"):
            return JsonResponse({"ok": False, "error": "invalid mode"}, status=400)
        from delayu.services.studio_import_risk import ImportRiskError

        rev = get_object_or_404(StudioConfigRevision, pk=int(rev_id), subsystem=m.subsystem)
        force = payload.get("force") is True
        try:
            result = studio_admin.restore_revision(
                m.subsystem, rev, request.user, mode=mode, force=force
            )
        except ImportRiskError as exc:
            return JsonResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    "blocked": True,
                    "risk": exc.risk,
                },
                status=409,
            )
        m.subsystem.refresh_from_db()
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.restore",
            "StudioConfigRevision",
            rev.pk,
            payload={
                "mode": mode,
                "from": rev.version_label,
                "forced": force and bool(result.get("restore_risk", {}).get("blocked")),
            },
            request=request,
        )
        return JsonResponse({"ok": True, **result, "has_draft": m.subsystem.studio_has_draft})


class StudioRestoreDryRunApiView(StudioMixin, View):
    """Предпросмотр отката к ревизии без применения."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        rev_id = payload.get("revision_id")
        mode = payload.get("mode", "draft")
        if not rev_id:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        if mode not in ("draft", "apply"):
            return JsonResponse({"ok": False, "error": "invalid mode"}, status=400)
        rev = get_object_or_404(StudioConfigRevision, pk=int(rev_id), subsystem=m.subsystem)
        try:
            result = studio_admin.dry_run_restore(m.subsystem, rev, mode=mode)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.dry_run.restore",
            "StudioConfigRevision",
            rev.pk,
            payload={
                "mode": mode,
                "from": rev.version_label,
                "changed_sections": (result.get("diff") or {}).get("changed_sections"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioBlueprintApplyApiView(StudioMixin, View):
    """Применить шаблон конфигурации в черновик."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        blueprint_id = payload.get("blueprint_id")
        package = payload.get("blueprint") or payload
        role_map = payload.get("role_map") or {}
        try:
            if blueprint_id and not payload.get("blueprint"):
                result = studio_admin.apply_blueprint(
                    m.subsystem, blueprint_id, role_map=role_map
                )
            else:
                result = studio_admin.apply_blueprint_package(
                    m.subsystem, package, role_map=role_map
                )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc) or "unknown blueprint"}, status=400)
        m.subsystem.refresh_from_db()
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.blueprint",
            "Subsystem",
            m.subsystem.pk,
            payload=result,
            request=request,
        )
        return JsonResponse({"ok": True, **result, "has_draft": m.subsystem.studio_has_draft})


class StudioBlueprintPreviewApiView(StudioMixin, View):
    """Предпросмотр шаблона конфигурации без применения."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        blueprint_id = (payload.get("blueprint_id") or "").strip()
        if not blueprint_id:
            return JsonResponse({"ok": False, "error": "blueprint_id required"}, status=400)
        role_map = payload.get("role_map") or {}
        try:
            result = studio_admin.preview_blueprint(
                m.subsystem, blueprint_id, role_map=role_map
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        return JsonResponse(result)


class StudioPackageDiffApiView(StudioMixin, View):
    """Сравнение пакета/текущего состояния с ревизией."""

    def get(self, request):
        m = _ctx_membership(self)
        rev_pk = request.GET.get("revision_id")
        if not rev_pk:
            return JsonResponse({"ok": False, "error": "revision_id required"}, status=400)
        include_draft = request.GET.get("include_draft", "1") != "0"
        try:
            result = studio_admin.compare_with_revision(
                m.subsystem, int(rev_pk), include_draft=include_draft
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=404)
        return JsonResponse(result)

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        package = payload.get("package") or payload
        to_draft = payload.get("to_draft", True) is not False
        rev_pk = payload.get("revision_id")
        try:
            if rev_pk:
                rev = get_object_or_404(
                    StudioConfigRevision, pk=int(rev_pk), subsystem=m.subsystem
                )
                from delayu.services.studio_revision_compare import compare_snapshots_detailed

                incoming = package.get("snapshot") or package
                diff = compare_snapshots_detailed(rev.snapshot or {}, incoming)
                result = {
                    "ok": True,
                    "revision_label": rev.version_label,
                    "revision_id": rev.pk,
                    "diff": diff,
                    "entity_diffs": diff.get("entity_diffs") or {},
                    "policies_diff": diff.get("policies_diff") or {},
                    "has_detail_changes": diff.get("has_detail_changes"),
                }
            else:
                result = studio_admin.dry_run_import_package(
                    m.subsystem, package, to_draft=to_draft
                )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        if result.get("ok", True):
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.dry_run.package",
                "Subsystem",
                m.subsystem.pk,
                payload={
                    "revision_id": rev_pk,
                    "changed_sections": (
                        (result.get("diff") or {}).get("changed_sections")
                        if isinstance(result.get("diff"), dict)
                        else None
                    ),
                    "stats": result.get("stats"),
                },
                request=request,
            )
        return JsonResponse(result)


class StudioBlueprintDryRunApiView(StudioMixin, View):
    """Dry-run шаблона конфигурации без применения."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        blueprint_id = (payload.get("blueprint_id") or "").strip()
        role_map = payload.get("role_map") or {}
        package = payload.get("package")
        try:
            if package:
                result = studio_admin.dry_run_blueprint_package(
                    m.subsystem, package, role_map=role_map
                )
            elif blueprint_id:
                result = studio_admin.dry_run_blueprint(
                    m.subsystem, blueprint_id, role_map=role_map
                )
            else:
                return JsonResponse({"ok": False, "error": "blueprint_id or package required"}, status=400)
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.dry_run.blueprint",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "blueprint": blueprint_id or (result.get("blueprint") if result else ""),
                "changed_sections": (result.get("diff") or {}).get("changed_sections"),
                "overwrites_draft": result.get("overwrites_draft"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioBlueprintExportApiView(StudioMixin, View):
    """Скачать шаблон конфигурации как JSON."""

    def get(self, request, blueprint_id):
        try:
            package = studio_admin.get_blueprint_package(blueprint_id)
        except ValueError:
            return JsonResponse({"ok": False, "error": "unknown blueprint"}, status=404)
        response = JsonResponse(package)
        response["Content-Disposition"] = (
            f'attachment; filename="blueprint-{blueprint_id}.json"'
        )
        return response


class StudioFormSchemaDiffApiView(StudioMixin, View):
    """Сравнение текущей схемы формы с опубликованной ревизией."""

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.form_schema_diff import compare_form_schemas

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        schema_id = payload.get("schema_id")
        current = payload.get("schema") or []
        if not schema_id:
            return JsonResponse({"ok": False, "error": "schema_id required"}, status=400)
        form = get_object_or_404(FormSchema, pk=int(schema_id), subsystem=m.subsystem)
        revision_id = payload.get("revision_id")
        rev_pk = int(revision_id) if revision_id else None
        baseline = studio_admin.baseline_form_schema(
            m.subsystem, form.code, revision_id=rev_pk
        )
        result = compare_form_schemas(baseline, current)
        result["form_code"] = form.code
        if rev_pk:
            rev = StudioConfigRevision.objects.filter(
                subsystem=m.subsystem, pk=rev_pk
            ).first()
            result["revision_label"] = rev.version_label if rev else str(rev_pk)
        else:
            rev = (
                StudioConfigRevision.objects.filter(subsystem=m.subsystem)
                .order_by("-created_at")
                .first()
            )
            result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioMenuDiffApiView(StudioMixin, View):
    """Сравнение текущего меню с ревизией."""

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_menu_layouts

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        layout = studio.normalize_menu_layout(payload.get("layout") or [])
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_menu_layout(m.subsystem, revision_id=rev_pk)
        result = compare_menu_layouts(baseline, layout)
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioBpmDiffApiView(StudioMixin, View):
    """Сравнение текущего BPM-шаблона с ревизией."""

    module_code = "M33"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_bpm_templates

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        template_id = payload.get("template_id")
        if not template_id:
            return JsonResponse({"ok": False, "error": "template_id required"}, status=400)
        tpl = get_object_or_404(BPMTemplate, pk=int(template_id), subsystem=m.subsystem)
        diagram = payload.get("diagram") or {}
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_bpm_template(
            m.subsystem, tpl.code, revision_id=rev_pk
        )
        result = compare_bpm_templates(baseline, diagram)
        result["template_code"] = tpl.code
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioCorrespondenceDiffApiView(StudioMixin, View):
    """Сравнение маршрута СЭД с ревизией."""

    module_code = "M27"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_correspondence_workflows

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        workflow = payload.get("workflow") or {}
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_correspondence_workflow(
            m.subsystem, revision_id=rev_pk
        )
        result = compare_correspondence_workflows(baseline, workflow)
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioPoliciesDiffApiView(StudioMixin, View):
    """Сравнение политик с ревизией."""

    module_code = "M78"

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_policies

        rev_pk = request.GET.get("revision_id")
        rev_id = int(rev_pk) if rev_pk else None
        baseline = studio_admin.baseline_policies(m.subsystem, revision_id=rev_id)
        current = studio_admin.current_policies_snapshot(m.subsystem)
        compare_current = {
            "retention_years": current["retention_years"],
            "alert_days": current["alert_days"],
            "auto_purge": current["auto_purge"],
            "siem_enabled": current["siem_enabled"],
            "siem_webhook": current["siem_webhook"],
        }
        result = compare_policies(baseline, compare_current)
        rev = studio_admin._revision_snapshot(m.subsystem, rev_id)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioPrintDiffApiView(StudioMixin, View):
    """Сравнение печатной формы с ревизией."""

    module_code = "M29"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_print_templates

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        template_id = payload.get("template_id")
        if not template_id:
            return JsonResponse({"ok": False, "error": "template_id required"}, status=400)
        tpl = get_object_or_404(PrintTemplate, pk=int(template_id), subsystem=m.subsystem)
        body = payload.get("body") or ""
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_print_template(
            m.subsystem, tpl.code, revision_id=rev_pk
        )
        result = compare_print_templates(baseline, body)
        result["template_code"] = tpl.code
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioNsiDiffApiView(StudioMixin, View):
    """Сравнение справочника НСИ с ревизией."""

    module_code = "M73"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_nsi_classifier

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        classifier_id = payload.get("classifier_id")
        if not classifier_id:
            return JsonResponse({"ok": False, "error": "classifier_id required"}, status=400)
        clf = get_object_or_404(NSIClassifier, pk=int(classifier_id), subsystem=m.subsystem)
        values = payload.get("values") or []
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_nsi_classifier(
            m.subsystem, clf.code, revision_id=rev_pk
        )
        result = compare_nsi_classifier(
            baseline,
            values,
            after_meta={
                "name": clf.name,
                "description": clf.description,
                "is_active": clf.is_active,
            },
        )
        result["classifier_code"] = clf.code
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioIntegrationDiffApiView(StudioMixin, View):
    """Сравнение endpoint интеграции с ревизией."""

    module_code = "M42"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.config_diff import compare_integration_endpoint

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        endpoint_id = payload.get("endpoint_id")
        if not endpoint_id:
            return JsonResponse({"ok": False, "error": "endpoint_id required"}, status=400)
        ep = get_object_or_404(IntegrationEndpoint, pk=int(endpoint_id), subsystem=m.subsystem)
        cfg = dict(ep.config or {})
        if isinstance(payload.get("pipeline"), dict):
            cfg["pipeline"] = payload["pipeline"]
        smev_cfg = payload.get("smev_config")
        if isinstance(smev_cfg, dict):
            for key in ("transport", "url", "test_mode", "client_id"):
                if key in smev_cfg:
                    cfg[key] = smev_cfg[key]
        rev_pk = int(payload["revision_id"]) if payload.get("revision_id") else None
        baseline = studio_admin.baseline_integration_endpoint(
            m.subsystem, ep.code, revision_id=rev_pk
        )
        result = compare_integration_endpoint(
            baseline,
            {
                "endpoint_type": ep.endpoint_type,
                "is_active": ep.is_active,
                "max_retries": ep.max_retries,
                "config": cfg,
            },
        )
        result["endpoint_code"] = ep.code
        rev = studio_admin._revision_snapshot(m.subsystem, rev_pk)
        result["revision_label"] = rev.version_label if rev else "—"
        return JsonResponse(result)


class StudioCloneConfigApiView(StudioMixin, View):
    """Клонирование конфигурации в другую подсистему."""

    def post(self, request):
        m = _ctx_membership(self)
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        target_code = (payload.get("target_code") or "").strip()
        if not target_code:
            return JsonResponse({"ok": False, "error": "target_code required"}, status=400)
        target_membership = (
            SubsystemMembership.objects.filter(
                user=request.user, subsystem__code=target_code
            )
            .select_related("subsystem")
            .first()
        )
        if not target_membership:
            return JsonResponse(
                {"ok": False, "error": "Нет доступа к целевой подсистеме"},
                status=403,
            )
        if not request.user.is_superuser:
            from delayu.models import ModuleCatalog
            from delayu.services.role_inheritance import role_has_action

            if not SubsystemModule.objects.filter(
                subsystem=target_membership.subsystem,
                module__code="M01",
                enabled=True,
            ).exists():
                return JsonResponse(
                    {"ok": False, "error": "Модуль M01 не включён в целевой подсистеме"},
                    status=403,
                )
            mod = ModuleCatalog.objects.filter(code="M01").first()
            if not mod or not role_has_action(target_membership.role, mod, "change"):
                return JsonResponse(
                    {"ok": False, "error": "Недостаточно прав в целевой подсистеме"},
                    status=403,
                )
        to_draft = payload.get("to_draft", True) is not False
        include_draft = payload.get("include_draft", False) is True
        try:
            result = studio_admin.clone_studio_config(
                m.subsystem,
                target_membership.subsystem,
                to_draft=to_draft,
                include_draft=include_draft,
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.clone_config",
            "Subsystem",
            target_membership.subsystem.pk,
            payload={
                "source": m.subsystem.code,
                "target": target_code,
                "to_draft": to_draft,
                "include_draft": include_draft,
                "stats": result.get("stats"),
            },
            request=request,
        )
        audit.log_action(
            request.user,
            target_membership.subsystem,
            "studio.clone_import",
            "Subsystem",
            m.subsystem.pk,
            payload={
                "source": m.subsystem.code,
                "target": target_code,
                "to_draft": to_draft,
                "include_draft": include_draft,
                "stats": result.get("stats"),
            },
            request=request,
        )
        return JsonResponse(result)


class StudioSchedulePublishApiView(StudioMixin, View):
    """Отложенная публикация черновика."""

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_publish_schedule import set_scheduled_publish
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone as tz

        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        at_raw = (payload.get("at") or "").strip()
        at = parse_datetime(at_raw)
        if at is None:
            return JsonResponse({"ok": False, "error": "Некорректная дата"}, status=400)
        if tz.is_naive(at):
            at = tz.make_aware(at, tz.get_current_timezone())
        schedule_tags = payload.get("tags")
        if schedule_tags is not None and not isinstance(schedule_tags, list):
            if isinstance(schedule_tags, str):
                schedule_tags = [t.strip() for t in schedule_tags.split(",") if t.strip()]
            else:
                schedule_tags = []
        try:
            sched = set_scheduled_publish(
                m.subsystem,
                at,
                comment=payload.get("comment") or "",
                user_id=request.user.pk,
                tags=schedule_tags,
            )
        except ValueError as exc:
            return JsonResponse({"ok": False, "error": str(exc)}, status=400)
        audit.log_action(
            request.user,
            m.subsystem,
            "studio.schedule_publish",
            payload={"at": at_raw, "tags": sched.get("tags") or []},
            request=request,
        )
        return JsonResponse({"ok": True, "scheduled": sched})

    def delete(self, request):
        m = _ctx_membership(self)
        from delayu.services.studio_publish_schedule import cancel_scheduled_publish

        cancelled = cancel_scheduled_publish(m.subsystem)
        if cancelled:
            audit.log_action(
                request.user,
                m.subsystem,
                "studio.cancel_schedule",
                request=request,
            )
        return JsonResponse({"ok": True, "cancelled": cancelled})


class RegistryLookupApiView(ModulePermissionMixin, View):
    """API для lookup-полей: список записей и данные для автозаполнения."""

    module_code = "M23"

    def get(self, request):
        m = _ctx_membership(self)
        registry_code = request.GET.get("registry", "").strip()
        if not registry_code:
            return JsonResponse({"ok": False, "error": "registry required"}, status=400)
        from delayu.services.registry_lookup import registry_choices, registry_record_payload

        record_id = request.GET.get("id", "").strip()
        if record_id.isdigit():
            payload = registry_record_payload(m.subsystem, registry_code, int(record_id))
            if payload is None:
                return JsonResponse({"ok": False, "error": "not found"}, status=404)
            return JsonResponse({"ok": True, "record": payload})
        label_field = request.GET.get("label_field", "name").strip() or "name"
        items = registry_choices(m.subsystem, registry_code, label_field=label_field)
        return JsonResponse({"ok": True, "items": items})
