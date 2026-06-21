"""Студия ДелаЮ — визуальные конструкторы (drag-and-drop)."""
import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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
    UserDashboardLayout,
    UserProfile,
)
from delayu.services import audit, studio
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
    {"slug": "forms", "title": "Карточка дела / формы", "module": "M74", "icon": "ri-layout-4-line"},
    {"slug": "bpm", "title": "BPMN-процессы", "module": "M33", "icon": "ri-flow-chart"},
    {"slug": "menu", "title": "Меню подсистемы", "module": "M01", "icon": "ri-menu-line"},
    {"slug": "dashboard", "title": "Дашборд руководителя", "module": "M85", "icon": "ri-bar-chart-line"},
    {"slug": "correspondence", "title": "Маршрут СЭД", "module": "M27", "icon": "ri-mail-send-line"},
    {"slug": "print", "title": "Печатные формы", "module": "M29", "icon": "ri-printer-line"},
    {"slug": "permissions", "title": "Матрица прав", "module": "M02", "icon": "ri-shield-user-line"},
    {"slug": "nsi", "title": "Справочники НСИ", "module": "M73", "icon": "ri-list-check"},
    {"slug": "integration", "title": "Pipeline интеграций", "module": "M42", "icon": "ri-plug-line"},
    {"slug": "cabinet", "title": "Личный кабинет", "module": "M07", "icon": "ri-user-settings-line"},
]


STUDIO_URLS = {
    "forms": "platform-studio-forms",
    "bpm": "platform-studio-bpm",
    "menu": "platform-studio-menu",
    "dashboard": "platform-studio-dashboard",
    "correspondence": "platform-studio-correspondence",
    "print": "platform-studio-print",
    "permissions": "platform-studio-permissions",
    "nsi": "platform-studio-nsi",
    "integration": "platform-studio-integration",
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


class StudioHubView(StudioMixin, TemplateView):
    studio_slug = "hub"
    template_name = "platform/studio/hub.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Студия ДелаЮ"
        ctx["breadcrumbs"] = [{"label": "Студия ДелаЮ", "url": None}]
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
        return ctx


class StudioMenuEditorView(StudioMixin, TemplateView):
    studio_slug = "menu"
    template_name = "platform/studio/menu_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Конструктор меню"
        layout = m.subsystem.menu_layout or studio.default_menu_layout()
        ctx["layout_json"] = json.dumps(layout, ensure_ascii=False)
        ctx["all_items"] = studio.flat_menu_items()
        ctx["all_items_json"] = json.dumps(ctx["all_items"], ensure_ascii=False)
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
        layout = UserDashboardLayout.objects.filter(
            user=self.request.user, subsystem=m.subsystem, is_default=True
        ).first()
        if not layout:
            layout = UserDashboardLayout.objects.filter(
                user=self.request.user, subsystem=m.subsystem
            ).first()
        widgets = layout.widgets if layout and layout.widgets else [
            {"id": w["id"], "label": w["label"], "w": w["w"], "h": w["h"]}
            for w in studio.DASHBOARD_WIDGETS[:4]
        ]
        ctx["layout_obj"] = layout
        ctx["widgets_json"] = json.dumps(widgets, ensure_ascii=False)
        ctx["catalog_json"] = json.dumps(studio.DASHBOARD_WIDGETS, ensure_ascii=False)
        return ctx


class StudioCorrespondenceEditorView(StudioMixin, TemplateView):
    module_code = "M27"
    studio_slug = "correspondence"
    template_name = "platform/studio/correspondence_editor.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Маршрут корреспонденции"
        wf = m.subsystem.correspondence_workflow or studio.default_correspondence_workflow()
        ctx["workflow_json"] = json.dumps(wf, ensure_ascii=False)
        ctx["step_catalog"] = studio.CORR_WORKFLOW_STEPS
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

            perms = {
                p.module_id: p
                for p in RoleModulePermission.objects.filter(role=role).select_related("module")
            }
            for mod in ctx["modules"]:
                p = perms.get(mod.id)
                matrix.append(
                    {
                        "code": mod.code,
                        "name": mod.name,
                        "view": bool(p and p.can_view),
                        "create": bool(p and p.can_create),
                        "change": bool(p and p.can_change),
                        "delete": bool(p and p.can_delete),
                        "view_pii": bool(p and p.can_view_pii),
                        "export_pii": bool(p and p.can_export_pii),
                    }
                )
        ctx["matrix_json"] = json.dumps(matrix, ensure_ascii=False)
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
        return ctx


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
            m.subsystem.menu_layout = payload.get("layout") or []
            m.subsystem.save(update_fields=["menu_layout", "updated_at"])
        elif editor == "dashboard":
            widgets = payload.get("widgets") or []
            layout, _ = UserDashboardLayout.objects.get_or_create(
                user=request.user,
                subsystem=m.subsystem,
                name="Студия",
                defaults={"is_default": True, "widgets": widgets},
            )
            layout.widgets = widgets
            layout.is_default = True
            layout.save(update_fields=["widgets", "is_default", "updated_at"])
        elif editor == "correspondence":
            m.subsystem.correspondence_workflow = payload.get("workflow") or {}
            m.subsystem.save(update_fields=["correspondence_workflow", "updated_at"])
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
            from delayu.models import ModuleCatalog, RoleModulePermission

            modules = {mod.code: mod for mod in enabled_modules_for_subsystem(m.subsystem)}
            for row in payload.get("matrix") or []:
                mod = modules.get(row.get("code"))
                if not mod:
                    continue
                if not any(row.get(a) for a in ("view", "create", "change", "delete", "view_pii", "export_pii")):
                    RoleModulePermission.objects.filter(role=role, module=mod).delete()
                    continue
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults={
                        "can_view": row.get("view", False),
                        "can_create": row.get("create", False),
                        "can_change": row.get("change", False),
                        "can_delete": row.get("delete", False),
                        "can_view_pii": row.get("view_pii", False),
                        "can_export_pii": row.get("export_pii", False),
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

        audit.log_action(
            request.user,
            m.subsystem,
            f"studio.save.{editor}",
            "Studio",
            editor,
            payload={"keys": list(payload.keys())},
            request=request,
        )
        return JsonResponse({"ok": True})
