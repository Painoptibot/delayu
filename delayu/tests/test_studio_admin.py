"""Тесты волны 1: Студия — черновики, публикация, health-check."""
import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from delayu.models import Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership
from delayu.models import BPMTask, IntegrationEndpoint, NSIClassifier
from delayu.services import studio, studio_admin
from delayu.services.demo_mode import blocks_mutation, is_demo_mode

User = get_user_model()


class StudioAdminWave1Tests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(code="test", name="Тест", status="active")
        self.org = Organization.objects.create(subsystem=self.sub, code="main", name="Главная")
        self.role = Role.objects.create(subsystem=self.sub, code="admin", name="Админ")
        self.user = User.objects.create_user(username="studio_admin", password="x")
        SubsystemMembership.objects.create(
            user=self.user,
            subsystem=self.sub,
            organization=self.org,
            role=self.role,
            is_default=True,
        )

    def test_save_and_publish_draft_menu(self):
        layout = [{"header": "Главная", "items": ["platform-home"]}]
        expected = studio.normalize_menu_layout(layout)
        studio_admin.save_draft(self.sub, "menu", layout)
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.studio_has_draft)
        self.assertEqual(self.sub.menu_layout, [])

        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="тест")
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.studio_has_draft)
        self.assertEqual(self.sub.menu_layout, expected)
        self.assertEqual(rev.version_label, "v2")
        self.assertIn("menu_layout", rev.snapshot)

    def test_health_checks_include_roles(self):
        checks = studio_admin.subsystem_health_checks(self.sub)
        ids = {c["id"] for c in checks}
        self.assertIn("roles", ids)
        self.assertIn("users", ids)
        roles_check = next(c for c in checks if c["id"] == "roles")
        self.assertEqual(roles_check["status"], "ok")

    def test_role_today_layout(self):
        from delayu.models import RoleStudioLayout, UserProfile

        studio_admin.save_role_layout(
            self.sub,
            self.role,
            RoleStudioLayout.Kind.TODAY,
            ["kpi_today", "tasks_table"],
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        widgets = studio.today_widgets_for_profile(
            profile, subsystem=self.sub, role=self.role
        )
        self.assertEqual(widgets, ["kpi_today", "tasks_table"])

    def test_superuser_not_in_demo_mode(self):
        from django.conf import settings

        old = settings.DELAYU_DEMO_MODE
        settings.DELAYU_DEMO_MODE = True
        try:
            rf = RequestFactory()
            request = rf.post("/cases/bulk/")
            request.user = self.user
            self.user.is_superuser = True
            self.assertFalse(is_demo_mode(request))
            self.assertFalse(blocks_mutation(request))
        finally:
            settings.DELAYU_DEMO_MODE = old

    def test_bpm_simulator(self):
        from delayu.services.bpm_simulator import simulate_diagram

        diagram = {
            "nodes": [
                {"id": "s", "type": "start", "label": "Старт"},
                {"id": "t1", "type": "task", "label": "Задача"},
                {"id": "e", "type": "end", "label": "Финиш"},
            ],
            "edges": [{"from": "s", "to": "t1"}, {"from": "t1", "to": "e"}],
        }
        result = simulate_diagram(diagram, hours_per_task=4)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["timeline"]), 3)
        self.assertEqual(result["total_hours"], 4)

    def test_export_import_package(self):
        studio_admin.save_draft(
            self.sub,
            "menu",
            [{"header": "Тест", "items": ["platform-home"]}],
        )
        package = studio_admin.export_config_package(self.sub)
        self.assertEqual(package["format"], "delayu-studio-package")
        other = Subsystem.objects.create(code="import_tgt", name="Импорт", status="active")
        Role.objects.create(subsystem=other, code="admin", name="Админ")
        stats = studio_admin.import_config_package(other, package, to_draft=True)
        other.refresh_from_db()
        self.assertTrue(stats["menu"])
        self.assertTrue(other.studio_has_draft)

    def test_form_visible_when(self):
        from delayu.services.form_schemas import field_visible, validate_schema_data

        schema = [
            {"key": "status", "label": "Статус", "type": "text"},
            {
                "key": "reason",
                "label": "Причина",
                "type": "text",
                "required": True,
                "visible_when": {"field": "status", "equals": "reject"},
            },
        ]
        self.assertFalse(field_visible(schema[1], {"status": "new"}))
        cleaned, errors = validate_schema_data(schema, {"status": "new"})
        self.assertNotIn("reason", errors)

    def test_menu_role_filter(self):
        from delayu.models import Organization
        from delayu.services.studio import menu_layout_to_menu_json, normalize_menu_layout

        org = Organization.objects.create(subsystem=self.sub, code="o1", name="Org")
        layout = normalize_menu_layout(
            [
                {
                    "header": "Тест",
                    "items": [
                        {"url": "platform-home", "roles": []},
                        {"url": "platform-cases", "roles": ["admin"]},
                    ],
                }
            ]
        )
        spec_role = Role.objects.create(subsystem=self.sub, code="spec", name="Спец")
        membership = SubsystemMembership.objects.create(
            user=self.user,
            subsystem=self.sub,
            organization=org,
            role=spec_role,
            is_default=True,
        )
        self.sub.menu_layout = layout
        menu = menu_layout_to_menu_json(layout, membership)
        names = [m.get("name") for m in menu if m.get("name")]
        self.assertIn("Главная", names)
        self.assertNotIn("Дела", names)

    def test_integration_dry_run(self):
        from delayu.services.studio_integration import dry_run_pipeline

        result = dry_run_pipeline(
            {
                "nodes": [
                    {"type": "source", "label": "Источник"},
                    {"type": "validate", "label": "Проверка", "required": ["title"]},
                    {"type": "endpoint", "label": "API"},
                ]
            }
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["log"]), 3)

    def test_action_permissions(self):
        from delayu.models import ModuleCatalog, SubsystemModule
        from delayu.services.access import user_can

        mod = ModuleCatalog.objects.filter(code="M22").first()
        if not mod:
            mod = ModuleCatalog.objects.create(code="M22", name="Дела", sort_order=22)
        SubsystemModule.objects.get_or_create(
            subsystem=self.sub, module=mod, defaults={"enabled": True}
        )
        perm, _ = RoleModulePermission.objects.get_or_create(
            role=self.role,
            module=mod,
            defaults={
                "can_view": True,
                "can_change": True,
                "can_bulk": False,
            },
        )
        perm.can_view = True
        perm.can_change = True
        perm.can_bulk = False
        perm.save(update_fields=["can_view", "can_change", "can_bulk"])
        self.assertTrue(user_can(self.user, "M22", "change"))
        self.assertFalse(user_can(self.user, "M22", "bulk"))
        perm.can_bulk = True
        perm.save(update_fields=["can_bulk"])
        self.assertTrue(user_can(self.user, "M22", "bulk"))

    def test_preview_as_role(self):
        from delayu.services.studio_admin import preview_as_role

        preview = preview_as_role(self.sub, self.role)
        self.assertEqual(preview["role"]["code"], "admin")
        self.assertIn("menu_sections", preview)
        self.assertIn("permissions", preview)

    def test_schema_sections_and_lookup(self):
        from delayu.services.form_schemas import normalize_schema, schema_sections

        schema = normalize_schema(
            [
                {"key": "sec1", "label": "Реквизиты", "type": "section"},
                {"key": "inn", "label": "ИНН", "type": "text"},
                {
                    "key": "org",
                    "label": "Организация",
                    "type": "lookup",
                    "registry_code": "orgs",
                    "fill_map": {"name": "org_name"},
                },
            ]
        )
        sections = schema_sections(schema)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["title"], "Реквизиты")
        self.assertEqual(sections[0]["fields"][1]["type"], "lookup")

    def test_menu_badges_and_pinned(self):
        from delayu.services.menu_badges import apply_menu_badges, inject_pinned_section
        from delayu.services.studio import normalize_menu_item, normalize_menu_layout

        item = normalize_menu_item(
            {"url": "platform-inbox", "badge": "inbox", "pinned": True, "roles": []}
        )
        self.assertEqual(item["badge"], "inbox")
        self.assertTrue(item["pinned"])
        layout = normalize_menu_layout([{"header": "X", "items": [item]}])
        self.assertEqual(layout[0]["items"][0]["badge"], "inbox")
        menu = inject_pinned_section(
            [{"menu_header": "X"}, {"url": "platform-cases", "name": "Дела"}],
            [{"url": "platform-inbox", "name": "Входящие", "badge_key": "inbox"}],
        )
        self.assertEqual(menu[0]["menu_header"], "Быстрый доступ")
        from delayu.services.menu_badges import badge_tuple

        self.assertEqual(badge_tuple("inbox", 3), ["primary", 3])
        self.assertIsNone(badge_tuple("inbox", 0))

    def test_role_inheritance(self):
        from delayu.models import ModuleCatalog, SubsystemModule
        from delayu.services.access import user_can
        from delayu.services.role_inheritance import effective_module_permission

        parent = Role.objects.create(subsystem=self.sub, code="mgr", name="Руководитель")
        child = Role.objects.create(
            subsystem=self.sub, code="clerk", name="Делопроизводитель", parent_role=parent
        )
        mod = ModuleCatalog.objects.filter(code="M22").first()
        if not mod:
            mod = ModuleCatalog.objects.create(code="M22", name="Дела", sort_order=22)
        SubsystemModule.objects.get_or_create(
            subsystem=self.sub, module=mod, defaults={"enabled": True}
        )
        RoleModulePermission.objects.create(
            role=parent,
            module=mod,
            can_view=True,
            can_bulk=True,
        )
        eff = effective_module_permission(child, mod)
        self.assertTrue(eff.can_view)
        self.assertTrue(eff.can_bulk)

        org = Organization.objects.create(subsystem=self.sub, code="o2", name="Org2")
        clerk_user = User.objects.create_user(username="clerk1", password="x")
        SubsystemMembership.objects.create(
            user=clerk_user,
            subsystem=self.sub,
            organization=org,
            role=child,
            is_default=True,
        )
        self.assertTrue(user_can(clerk_user, "M22", "bulk"))
        self.assertFalse(user_can(clerk_user, "M22", "delete"))

    def test_bpm_escalation_simulator(self):
        from delayu.services.bpm_simulator import simulate_diagram
        from delayu.services.studio import diagram_to_bpm_steps

        diagram = {
            "nodes": [
                {"id": "s", "type": "start", "label": "Старт"},
                {
                    "id": "t1",
                    "type": "task",
                    "label": "Согласование",
                    "duration_hours": 24,
                    "escalate_after_hours": 8,
                    "escalate_to_role": "mgr",
                },
                {"id": "e", "type": "end", "label": "Финиш"},
            ],
            "edges": [{"from": "s", "to": "t1"}, {"from": "t1", "to": "e"}],
        }
        result = simulate_diagram(diagram)
        self.assertTrue(result["ok"])
        types = [t["type"] for t in result["timeline"]]
        self.assertIn("escalation", types)
        steps = diagram_to_bpm_steps(diagram)
        self.assertEqual(steps[0]["escalate_after_hours"], 8)
        self.assertEqual(steps[0]["escalate_to_role"], "mgr")

    def test_preview_includes_inherited_permissions(self):
        from delayu.models import ModuleCatalog, SubsystemModule
        from delayu.services.studio_admin import preview_as_role

        parent = Role.objects.create(subsystem=self.sub, code="p1", name="База")
        child = Role.objects.create(
            subsystem=self.sub, code="c1", name="Наследник", parent_role=parent
        )
        mod = ModuleCatalog.objects.filter(code="M02").first()
        if not mod:
            mod = ModuleCatalog.objects.create(code="M02", name="Админ", sort_order=2)
        SubsystemModule.objects.get_or_create(
            subsystem=self.sub, module=mod, defaults={"enabled": True}
        )
        RoleModulePermission.objects.create(role=parent, module=mod, can_view=True)
        preview = preview_as_role(self.sub, child)
        codes = {p["code"] for p in preview["permissions"]}
        self.assertIn("M02", codes)

    def test_bpm_runtime_escalation(self):
        from datetime import timedelta

        from django.contrib.auth import get_user_model
        from django.utils import timezone

        from delayu.models import BPMInstance, BPMTemplate, CaseFile
        from delayu.services.bpm_escalation import process_bpm_escalations

        User = get_user_model()
        mgr = Role.objects.create(subsystem=self.sub, code="mgr", name="Руководитель")
        clerk_role = Role.objects.create(subsystem=self.sub, code="clerk", name="Клерк")
        clerk = User.objects.create_user(username="clerk_bpm", password="x")
        manager = User.objects.create_user(username="mgr_bpm", password="x")
        org = Organization.objects.create(subsystem=self.sub, code="o3", name="Org3")
        SubsystemMembership.objects.create(
            user=clerk, subsystem=self.sub, organization=org, role=clerk_role, is_default=True
        )
        SubsystemMembership.objects.create(
            user=manager, subsystem=self.sub, organization=org, role=mgr, is_default=True
        )
        case = CaseFile.objects.create(
            subsystem=self.sub,
            organization=org,
            number="BPM-1",
            title="Тест эскалации",
            assignee=clerk,
            created_by=self.user,
        )
        tpl = BPMTemplate.objects.create(
            subsystem=self.sub,
            code="esc",
            name="Эскалация",
            steps=[
                {
                    "id": "s1",
                    "name": "Согласование",
                    "escalate_after_hours": 1,
                    "escalate_to_role": "mgr",
                }
            ],
        )
        inst = BPMInstance.objects.create(template=tpl, case=case, current_step_id="s1")
        task = BPMTask.objects.create(
            instance=inst,
            step_id="s1",
            step_name="Согласование",
            assignee=clerk,
            assigned_at=timezone.now() - timedelta(hours=5),
        )
        result = process_bpm_escalations(self.sub)
        self.assertEqual(result["escalated"], 1)
        task.refresh_from_db()
        self.assertTrue(task.is_escalated)
        self.assertEqual(task.assignee_id, manager.pk)

    def test_preview_as_membership(self):
        from delayu.services.studio_admin import preview_as_membership

        mem = SubsystemMembership.objects.get(user=self.user, subsystem=self.sub)
        preview = preview_as_membership(self.sub, mem)
        self.assertEqual(preview["user"]["username"], "studio_admin")
        self.assertIn("permission_matrix", preview)

    def test_siem_payload_builder(self):
        from delayu.services.audit import log_action
        from delayu.services.siem_export import build_siem_payload, get_or_create_siem_config

        log_action(self.user, self.sub, "test.siem", "Case", "1")
        events = build_siem_payload(self.sub, limit=10)
        self.assertTrue(any(e["action"] == "test.siem" for e in events))
        cfg = get_or_create_siem_config(self.sub)
        self.assertFalse(cfg.enabled)

    def test_revision_compare(self):
        from delayu.services.studio_admin import capture_snapshot
        from delayu.services.studio_revision_compare import compare_snapshots

        snap_a = capture_snapshot(self.sub)
        snap_b = dict(snap_a)
        snap_b["menu_layout"] = [{"header": "X", "items": ["platform-home", "platform-cases"]}]
        diff = compare_snapshots(snap_a, snap_b)
        self.assertGreater(diff["changed_sections"], 0)
        keys = {s["key"] for s in diff["sections"]}
        self.assertIn("menu_layout", keys)

    def test_smev_pipeline_dry_run(self):
        from delayu.services.studio_integration import dry_run_pipeline

        result = dry_run_pipeline(
            {
                "nodes": [
                    {"type": "source", "label": "Источник"},
                    {"type": "smev", "label": "СМЭВ", "message_type": "Request"},
                    {"type": "endpoint", "label": "API"},
                ]
            }
        )
        self.assertTrue(result["ok"])
        self.assertIn("smev_envelope", result["output"])
        types = [x["type"] for x in result["log"]]
        self.assertIn("smev", types)

    def test_form_schema_diff(self):
        from delayu.services.form_schema_diff import compare_form_schemas

        before = [{"key": "a", "label": "Поле A", "type": "text"}]
        after = [
            {"key": "a", "label": "Поле A (новое)", "type": "text"},
            {"key": "b", "label": "Поле B", "type": "number"},
        ]
        diff = compare_form_schemas(before, after)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(len(diff["changed"]), 1)
        self.assertEqual(diff["changed"][0]["key"], "a")

    def test_restore_revision_draft(self):
        from delayu.models import FormSchema, StudioConfigRevision

        FormSchema.objects.create(
            subsystem=self.sub,
            code="case_main",
            name="Дело",
            target="case",
            schema=[{"key": "x", "label": "X", "type": "text"}],
        )
        snap = studio_admin.capture_snapshot(self.sub)
        rev = StudioConfigRevision.objects.create(
            subsystem=self.sub,
            version_label="v1",
            snapshot=snap,
            published_by=self.user,
        )
        FormSchema.objects.filter(subsystem=self.sub, code="case_main").update(
            schema=[{"key": "y", "label": "Y", "type": "text"}]
        )
        studio_admin.save_draft(
            self.sub,
            "menu",
            [{"header": "Тест", "items": [{"url": "platform-home", "roles": []}]}],
        )
        result = studio_admin.restore_revision(self.sub, rev, self.user, mode="draft")
        self.sub.refresh_from_db()
        self.assertEqual(result["mode"], "draft")
        self.assertTrue(self.sub.studio_has_draft)
        self.assertIn("menu", self.sub.studio_draft)
        restored = FormSchema.objects.get(subsystem=self.sub, code="case_main")
        self.assertEqual(restored.schema[0]["key"], "x")

    def test_apply_blueprint(self):
        from delayu.models import RoleStudioLayout

        operator = Role.objects.create(subsystem=self.sub, code="operator", name="Оператор")
        result = studio_admin.apply_blueprint(self.sub, "operator_daily")
        self.sub.refresh_from_db()
        self.assertIn("menu", result["applied"])
        self.assertIn("role_layouts", result["applied"])
        self.assertEqual(result["role_layouts"], 2)
        self.assertTrue(self.sub.studio_has_draft)
        today = RoleStudioLayout.objects.get(
            subsystem=self.sub, role=operator, kind=RoleStudioLayout.Kind.TODAY
        )
        self.assertIn("kpi_today", today.widgets)

    def test_apply_snapshot_nsi_integrations(self):
        from delayu.models import StudioConfigRevision

        NSIClassifier.objects.create(
            subsystem=self.sub, code="regions", name="Регионы", description="Старое"
        )
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="smev_gw",
            name="СМЭВ",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={"url": "https://old.example"},
        )
        snap = studio_admin.capture_snapshot(self.sub)
        NSIClassifier.objects.filter(subsystem=self.sub, code="regions").update(
            name="Изменено", description="Новое"
        )
        IntegrationEndpoint.objects.filter(subsystem=self.sub, code="smev_gw").update(
            config={"url": "https://new.example"}
        )
        rev = StudioConfigRevision.objects.create(
            subsystem=self.sub,
            version_label="v1",
            snapshot=snap,
            published_by=self.user,
        )
        studio_admin.restore_revision(self.sub, rev, self.user, mode="apply")
        nsi = NSIClassifier.objects.get(subsystem=self.sub, code="regions")
        self.assertEqual(nsi.name, "Регионы")
        self.assertEqual(nsi.description, "Старое")
        endpoint = IntegrationEndpoint.objects.get(subsystem=self.sub, code="smev_gw")
        self.assertEqual(endpoint.config.get("url"), "https://old.example")

    def test_form_diff_by_revision(self):
        from delayu.models import FormSchema, StudioConfigRevision
        from delayu.services.form_schema_diff import compare_form_schemas

        FormSchema.objects.create(
            subsystem=self.sub,
            code="case_main",
            name="Дело",
            target="case",
            schema=[{"key": "a", "label": "A", "type": "text"}],
        )
        snap_v1 = studio_admin.capture_snapshot(self.sub)
        rev1 = StudioConfigRevision.objects.create(
            subsystem=self.sub,
            version_label="v1",
            snapshot=snap_v1,
            published_by=self.user,
        )
        FormSchema.objects.filter(subsystem=self.sub, code="case_main").update(
            schema=[{"key": "a", "label": "A", "type": "text"}, {"key": "b", "label": "B", "type": "number"}]
        )
        snap_v2 = studio_admin.capture_snapshot(self.sub)
        StudioConfigRevision.objects.create(
            subsystem=self.sub,
            version_label="v2",
            snapshot=snap_v2,
            published_by=self.user,
        )
        baseline_v1 = studio_admin.baseline_form_schema(
            self.sub, "case_main", revision_id=rev1.pk
        )
        current = FormSchema.objects.get(subsystem=self.sub, code="case_main").schema
        diff = compare_form_schemas(baseline_v1, current)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["key"], "b")

    def test_import_policies_in_draft_mode(self):
        from delayu.services.retention import get_or_create_retention_policy
        from delayu.services.siem_export import get_or_create_siem_config

        retention = get_or_create_retention_policy(self.sub)
        retention.default_archive_years = 3
        retention.save()
        siem = get_or_create_siem_config(self.sub)
        siem.enabled = True
        siem.webhook_url = "https://siem.example/hook"
        siem.save()
        package = studio_admin.export_config_package(self.sub)
        retention.default_archive_years = 99
        retention.save()
        siem.enabled = False
        siem.save()
        stats = studio_admin.import_config_package(self.sub, package, to_draft=True)
        self.assertTrue(stats["policies"])
        retention.refresh_from_db()
        siem.refresh_from_db()
        self.assertEqual(retention.default_archive_years, 3)
        self.assertTrue(siem.enabled)

    def test_smev_runtime_simulated(self):
        from delayu.models import IntegrationMessage
        from delayu.services.integrations import enqueue_outbound, process_outbound
        from delayu.services.smev_runtime import build_smev_envelope, process_smev_message

        ep = IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="smev_rt",
            name="СМЭВ RT",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={"transport": "simulated", "test_mode": True},
        )
        env = build_smev_envelope({"message_type": "Request", "body": {"x": 1}}, ep.config)
        self.assertEqual(env["message_type"], "Request")
        msg = enqueue_outbound(ep, {"message_type": "Request", "body": {"title": "T"}})
        msg = process_smev_message(msg)
        self.assertEqual(msg.status, IntegrationMessage.Status.SENT)
        self.assertIn("smev_envelope", msg.payload)
        msg2 = enqueue_outbound(ep, {"message_type": "Request", "body": {}})
        msg2 = process_outbound(msg2)
        self.assertEqual(msg2.status, IntegrationMessage.Status.SENT)

    def test_run_pipeline_runtime(self):
        from delayu.services.studio_integration import run_pipeline

        ep = IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="smev_pipe",
            name="СМЭВ pipe",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={"transport": "simulated"},
        )
        result = run_pipeline(
            {
                "nodes": [
                    {"type": "source", "label": "Источник"},
                    {"type": "smev", "label": "СМЭВ", "message_type": "Request"},
                ]
            },
            mode="runtime",
            endpoint=ep,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "runtime")
        self.assertIn("smev_message_id", result["output"])

    def test_setup_wizard_progress(self):
        from delayu.services.studio_setup import build_setup_steps, ensure_smev_stub_endpoint, setup_progress

        progress = setup_progress(self.sub)
        self.assertGreater(progress["total"], 0)
        steps = build_setup_steps(self.sub)
        self.assertTrue(any(s["id"] == "roles" and s["done"] for s in steps))
        ensure_smev_stub_endpoint(self.sub)
        progress2 = setup_progress(self.sub)
        integrations = next(s for s in progress2["steps"] if s["id"] == "integrations")
        self.assertTrue(integrations["done"])

    def test_menu_diff_by_revision(self):
        from delayu.services.config_diff import compare_menu_layouts

        layout_v1 = [{"header": "A", "items": [{"url": "platform-home", "roles": []}]}]
        studio_admin.save_draft(self.sub, "menu", layout_v1)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="v1")
        layout_v2 = [
            {
                "header": "A",
                "items": [
                    {"url": "platform-home", "roles": ["admin"]},
                    {"url": "platform-cases", "roles": []},
                ],
            }
        ]
        baseline = studio_admin.baseline_menu_layout(self.sub, revision_id=rev.pk)
        diff = compare_menu_layouts(baseline, layout_v2)
        self.assertEqual(len(diff["added"]), 1)
        self.assertEqual(diff["added"][0]["url"], "platform-cases")
        self.assertEqual(len(diff["changed"]), 1)

    def test_bpm_diff_by_revision(self):
        from delayu.models import BPMTemplate
        from delayu.services.config_diff import compare_bpm_templates

        tpl = BPMTemplate.objects.create(
            subsystem=self.sub,
            code="wf1",
            name="WF",
            diagram={
                "nodes": [{"id": "n1", "type": "task", "label": "A"}],
                "edges": [],
            },
            steps=[],
        )
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="bpm")
        baseline = studio_admin.baseline_bpm_template(self.sub, "wf1", revision_id=rev.pk)
        after = {
            "nodes": [
                {"id": "n1", "type": "task", "label": "A", "form_schema_code": "x"},
                {"id": "n2", "type": "approval", "label": "B"},
            ],
            "edges": [{"from": "n1", "to": "n2"}],
        }
        diff = compare_bpm_templates(baseline, after)
        self.assertEqual(len(diff["added"]), 1)
        self.assertTrue(diff["edges_changed"])

    def test_auto_launch_setup(self):
        from delayu.services.studio_setup import init_setup_for_new_subsystem, should_auto_launch_setup

        sub = Subsystem.objects.create(code="newsub", name="Новая", status="active")
        init_setup_for_new_subsystem(sub)
        sub.refresh_from_db()
        self.assertTrue(should_auto_launch_setup(sub))
        studio_admin.publish_studio_draft(self.sub, self.user)
        self.assertFalse(should_auto_launch_setup(self.sub))

    def test_smev_production_headers(self):
        from delayu.services.smev_runtime import build_smev_envelope, is_production_transport, smev_http_headers

        config = {"transport": "http", "test_mode": False, "client_id": "c1"}
        self.assertTrue(is_production_transport(config))
        env = build_smev_envelope({"message_type": "Request", "body": {}}, config)
        headers = smev_http_headers(config, env)
        self.assertEqual(headers["X-SMEV-Production"], "1")
        self.assertNotIn("X-SMEV-Test", headers)

    def test_provision_inits_setup(self):
        from delayu.services.studio_setup import should_auto_launch_setup
        from delayu.services.subsystems import provision_subsystem

        sub = Subsystem.objects.create(code="prov", name="Prov", status="draft")
        provision_subsystem(sub, ["M01", "M02"])
        sub.refresh_from_db()
        self.assertTrue(sub.studio_setup_state.get("auto_launch"))
        self.assertTrue(should_auto_launch_setup(sub))

    def test_correspondence_diff(self):
        from delayu.services.config_diff import compare_correspondence_workflows

        wf1 = {"steps": ["register", "assign", "execute"], "sla_days": {"register": 1, "assign": 2}}
        studio_admin.save_draft(self.sub, "correspondence", wf1)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        wf2 = {
            "steps": ["register", "execute", "assign"],
            "sla_days": {"register": 1, "assign": 5, "execute": 10},
        }
        baseline = studio_admin.baseline_correspondence_workflow(self.sub, revision_id=rev.pk)
        diff = compare_correspondence_workflows(baseline, wf2)
        self.assertTrue(diff["moved_steps"])
        self.assertTrue(diff["sla_changed"])

    def test_policies_diff(self):
        from delayu.services.config_diff import compare_policies

        studio_admin.publish_studio_draft(self.sub, self.user)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="p2")
        baseline = studio_admin.baseline_policies(self.sub, revision_id=rev.pk)
        current = studio_admin.current_policies_snapshot(self.sub)
        compare_current = {
            "retention_years": 99,
            "alert_days": current["alert_days"],
            "auto_purge": current["auto_purge"],
            "siem_enabled": current["siem_enabled"],
            "siem_webhook": current["siem_webhook"],
        }
        diff = compare_policies(baseline, compare_current)
        self.assertTrue(diff["changed"])

    def test_blueprint_export_package(self):
        package = studio_admin.get_blueprint_package("operator_daily")
        self.assertEqual(package["format"], "delayu-blueprint")
        self.assertEqual(package["blueprint"]["id"], "operator_daily")

    def test_print_diff(self):
        from delayu.models_business import PrintTemplate
        from delayu.services.config_diff import compare_print_templates

        tpl = PrintTemplate.objects.create(
            subsystem=self.sub,
            code="letter",
            name="Письмо",
            body="<p>{{reg_number}}</p>",
        )
        studio_admin.publish_studio_draft(self.sub, self.user)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="print")
        baseline = studio_admin.baseline_print_template(self.sub, "letter", revision_id=rev.pk)
        diff = compare_print_templates(baseline, "<p>{{reg_number}} {{subject}}</p>")
        self.assertTrue(diff["body_changed"])
        self.assertIn("subject", diff["added_variables"])

    def test_clone_studio_config(self):
        target = Subsystem.objects.create(code="target", name="Цель", status="active")
        target_org = Organization.objects.create(subsystem=target, code="main", name="Главная")
        target_role = Role.objects.create(subsystem=target, code="admin", name="Админ")
        SubsystemMembership.objects.create(
            user=self.user,
            subsystem=target,
            organization=target_org,
            role=target_role,
        )
        layout = [{"header": "Главная", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.publish_studio_draft(self.sub, self.user)
        result = studio_admin.clone_studio_config(self.sub, target, to_draft=True)
        self.assertTrue(result["ok"])
        target.refresh_from_db()
        self.assertTrue(target.studio_has_draft)
        self.assertEqual(len(target.studio_draft.get("menu", [])), 1)

    def test_scheduled_publish(self):
        from datetime import timedelta

        from django.utils import timezone

        from delayu.services.studio_publish_schedule import (
            cancel_scheduled_publish,
            get_scheduled_publish,
            process_due_scheduled_publishes,
            set_scheduled_publish,
        )

        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        future = timezone.now() + timedelta(hours=2)
        set_scheduled_publish(self.sub, future, comment="ночь", user_id=self.user.pk)
        self.assertIsNotNone(get_scheduled_publish(self.sub))
        cancel_scheduled_publish(self.sub)
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.sub.studio_setup_state = {
            "scheduled_publish": {
                "at": past_at,
                "comment": "сейчас",
                "user_id": self.user.pk,
            }
        }
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        result = process_due_scheduled_publishes()
        self.assertIn(self.sub.code, result["published"])
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.studio_has_draft)
        self.assertIsNone(get_scheduled_publish(self.sub))

    def test_nsi_diff(self):
        from delayu.models import NSIClassifier, NSIValue
        from delayu.services.config_diff import compare_nsi_classifier

        clf = NSIClassifier.objects.create(
            subsystem=self.sub, code="regions", name="Регионы", description="old"
        )
        NSIValue.objects.create(classifier=clf, code="msk", name="Москва", sort_order=1)
        studio_admin.publish_studio_draft(self.sub, self.user)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="nsi")
        baseline = studio_admin.baseline_nsi_classifier(self.sub, "regions", revision_id=rev.pk)
        after_values = [{"code": "msk", "name": "Москва"}, {"code": "spb", "name": "СПб"}]
        diff = compare_nsi_classifier(
            baseline,
            after_values,
            after_meta={"name": "Регионы", "description": "new", "is_active": True},
        )
        self.assertIn("spb", diff["added_values"])
        self.assertTrue(diff["meta_changed"])

    def test_integration_diff(self):
        from delayu.services.config_diff import compare_integration_endpoint

        ep = IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="smev1",
            name="СМЭВ",
            endpoint_type="smev",
            config={"pipeline": {"nodes": [{"type": "source", "label": "A"}]}, "transport": "simulated"},
        )
        studio_admin.publish_studio_draft(self.sub, self.user)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="int")
        baseline = studio_admin.baseline_integration_endpoint(self.sub, "smev1", revision_id=rev.pk)
        after = {
            "endpoint_type": ep.endpoint_type,
            "is_active": ep.is_active,
            "max_retries": ep.max_retries,
            "config": {
                "pipeline": {
                    "nodes": [
                        {"type": "source", "label": "A"},
                        {"type": "smev", "label": "СМЭВ"},
                    ]
                },
                "transport": "http",
            },
        }
        diff = compare_integration_endpoint(baseline, after)
        self.assertTrue(diff["pipeline_changed"])
        self.assertTrue(diff["smev_changed"])

    def test_blueprint_role_map(self):
        from delayu.models import RoleStudioLayout

        op = Role.objects.create(subsystem=self.sub, code="spec", name="Специалист")
        result = studio_admin.apply_blueprint(
            self.sub, "operator_daily", role_map={"operator": "spec"}
        )
        self.assertIn("role_layouts", result["applied"])
        self.assertTrue(
            RoleStudioLayout.objects.filter(
                subsystem=self.sub, role=op, kind=RoleStudioLayout.Kind.TODAY
            ).exists()
        )

    def test_form_diff_by_section(self):
        from delayu.services.form_schema_diff import compare_form_schemas

        before = [
            {"key": "a", "label": "A", "type": "text", "section": "Основное"},
            {"key": "b", "label": "B", "type": "text", "section": "Дополнительно"},
        ]
        after = [
            {"key": "a", "label": "A2", "type": "text", "section": "Основное"},
            {"key": "c", "label": "C", "type": "text", "section": "Дополнительно"},
        ]
        diff = compare_form_schemas(before, after)
        self.assertIn("Основное", diff["by_section"])
        self.assertTrue(diff["by_section"]["Основное"]["changed"])
        self.assertTrue(diff["by_section"]["Дополнительно"]["added"])

    def test_blueprint_preview(self):
        preview = studio_admin.preview_blueprint(self.sub, "operator_daily")
        self.assertTrue(preview["ok"])
        self.assertIn("menu", preview["draft_sections"])
        self.assertGreater(preview["menu_items"], 0)

    def test_scheduled_publish_notification(self):
        from datetime import timedelta

        from django.utils import timezone

        from delayu.models import Notification
        from delayu.services.studio_publish_schedule import (
            get_scheduled_publish,
            process_due_scheduled_publishes,
        )

        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.sub.studio_setup_state = {
            "scheduled_publish": {
                "at": past_at,
                "comment": "ночная публикация",
                "user_id": self.user.pk,
            }
        }
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        result = process_due_scheduled_publishes()
        self.assertIn(self.sub.code, result["published"])
        note = Notification.objects.filter(
            user=self.user, subsystem=self.sub, title__contains="Студия"
        ).first()
        self.assertIsNotNone(note)
        self.assertIn("ночная", note.body)
        self.assertIsNone(get_scheduled_publish(self.sub))

    def test_compare_with_revision(self):
        layout = [{"header": "A", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        studio_admin.save_draft(
            self.sub, "menu", [{"header": "B", "items": ["platform-cases"]}]
        )
        result = studio_admin.compare_with_revision(self.sub, rev.pk, include_draft=True)
        self.assertTrue(result["ok"])
        self.assertGreater(result["diff"]["changed_sections"], 0)

    def test_dry_run_blueprint(self):
        result = studio_admin.dry_run_blueprint(self.sub, "operator_daily")
        self.assertTrue(result["dry_run"])
        self.assertIn("diff", result)

    def test_dry_run_import_package(self):
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["forms"] = []
        result = studio_admin.dry_run_import_package(self.sub, package)
        self.assertTrue(result["ok"])
        self.assertIn("diff", result)

    def test_scheduled_publish_email(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        from delayu.services.studio_publish_schedule import process_due_scheduled_publishes

        self.user.email = "studio@test.local"
        self.user.save(update_fields=["email"])
        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.sub.studio_setup_state = {
            "scheduled_publish": {
                "at": past_at,
                "comment": "email test",
                "user_id": self.user.pk,
            }
        }
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        with patch("delayu.services.mail.send_mail_message") as mail_mock:
            mail_mock.return_value = (True, "")
            process_due_scheduled_publishes()
            self.assertTrue(mail_mock.called)
            self.assertEqual(mail_mock.call_args.kwargs["to_addrs"], ["studio@test.local"])

    def test_validate_config_package(self):
        from delayu.services.studio_package_validate import validate_config_package

        good = studio_admin.export_config_package(self.sub)
        result = validate_config_package(good)
        self.assertTrue(result["ok"])
        bad = {"format": "delayu-studio-package", "snapshot": {"forms": [{"name": "x"}]}}
        bad_result = validate_config_package(bad)
        self.assertFalse(bad_result["ok"])
        self.assertTrue(any("code" in e for e in bad_result["errors"]))

    def test_import_rejects_invalid_package(self):
        with self.assertRaises(ValueError):
            studio_admin.import_config_package(
                self.sub, {"format": "delayu-studio-package", "snapshot": {"bpm": ["bad"]}}
            )

    def test_dry_run_audit_blueprint(self):
        from delayu.models_business import AuditLog

        from delayu.views_studio import StudioBlueprintDryRunApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/blueprints/dry-run/",
            data='{"blueprint_id":"operator_daily"}',
            content_type="application/json",
        )
        request.user = self.user
        response = StudioBlueprintDryRunApiView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            AuditLog.objects.filter(
                subsystem=self.sub, action="studio.dry_run.blueprint"
            ).exists()
        )

    def test_scheduled_publish_telegram(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        from delayu.models import UserProfile
        from delayu.services.studio_publish_schedule import process_due_scheduled_publishes

        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.telegram_chat_id = "12345"
        profile.save(update_fields=["telegram_chat_id"])
        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.sub.studio_setup_state = {
            "scheduled_publish": {
                "at": past_at,
                "comment": "tg test",
                "user_id": self.user.pk,
            }
        }
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        with patch("delayu.services.telegram.send_telegram_message", return_value=True) as tg_mock:
            process_due_scheduled_publishes()
            self.assertTrue(tg_mock.called)

    def test_evaluate_import_risk_blocked(self):
        from delayu.services.studio_import_risk import evaluate_import_risk

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="risk_ep",
            name="Риск",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        current = studio_admin.effective_snapshot(self.sub)
        incoming = dict(current)
        incoming["integrations"] = []
        risk = evaluate_import_risk(current, incoming)
        self.assertTrue(risk["blocked"])
        self.assertTrue(any(r["key"] == "integrations" for r in risk["critical"]))

    def test_import_blocked_without_force(self):
        from delayu.services.studio_import_risk import ImportRiskError

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="risk_ep",
            name="Риск",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["integrations"] = []
        with self.assertRaises(ImportRiskError):
            studio_admin.import_config_package(self.sub, package, to_draft=True, force=False)

    def test_import_with_force(self):
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="risk_ep",
            name="Риск",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["integrations"] = []
        stats = studio_admin.import_config_package(self.sub, package, to_draft=True, force=True)
        self.assertIn("import_risk", stats)
        self.assertTrue(stats["import_risk"]["blocked"])

    def test_dry_run_import_includes_risk(self):
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["integrations"] = []
        result = studio_admin.dry_run_import_package(self.sub, package)
        self.assertTrue(result["ok"])
        self.assertIn("risk", result)

    def test_validate_blueprint_package(self):
        from delayu.services.studio_package_validate import validate_blueprint_package

        good = {
            "format": "delayu-blueprint",
            "blueprint": {
                "id": "custom",
                "menu": [{"header": "A", "items": []}],
            },
        }
        self.assertTrue(validate_blueprint_package(good)["ok"])
        bad = {"format": "delayu-blueprint", "blueprint": {"menu": "not-a-list"}}
        bad_result = validate_blueprint_package(bad)
        self.assertFalse(bad_result["ok"])

    def test_apply_blueprint_rejects_invalid(self):
        with self.assertRaises(ValueError):
            studio_admin.apply_blueprint_package(
                self.sub,
                {"format": "delayu-blueprint", "blueprint": {"role_layouts": "bad"}},
            )

    def test_ensure_studio_notification_templates(self):
        from delayu.models_business import NotificationTemplate
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        created = ensure_studio_notification_templates(self.sub)
        self.assertGreaterEqual(created, 1)
        self.assertEqual(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio_scheduled_publish"
            ).count(),
            3,
        )
        self.assertTrue(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.config_published"
            ).exists()
        )
        self.assertTrue(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.config_restored"
            ).exists()
        )

    def test_import_api_blocked_409(self):
        from delayu.views_studio import StudioImportConfigApiView

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="risk_ep",
            name="Риск",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["integrations"] = []
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/import/",
            data=json.dumps(package),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioImportConfigApiView.as_view()(request)
        self.assertEqual(response.status_code, 409)
        payload = json.loads(response.content)
        self.assertTrue(payload.get("blocked"))
        self.assertIn("risk", payload)

    def test_scheduled_publish_uses_templates(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        from delayu.services.studio_notification_templates import ensure_studio_notification_templates
        from delayu.services.studio_publish_schedule import process_due_scheduled_publishes

        ensure_studio_notification_templates(self.sub)
        self.user.email = "studio@test.local"
        self.user.save(update_fields=["email"])
        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        self.sub.studio_setup_state = {
            "scheduled_publish": {
                "at": past_at,
                "comment": "template test",
                "user_id": self.user.pk,
            }
        }
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        with patch("delayu.services.notify_dispatch.dispatch_event") as dispatch_mock:
            process_due_scheduled_publishes()
            self.assertTrue(dispatch_mock.called)
            self.assertEqual(dispatch_mock.call_args.args[1], "studio_scheduled_publish")

    def test_publish_emits_studio_webhook(self):
        from delayu.models import IntegrationMessage, StudioConfigRevision

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_wh",
            name="Studio WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/studio-hook",
                "events": ["studio.config_published"],
            },
        )
        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="wh test")
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.config_published")
        self.assertEqual(msg.payload["data"]["version"], rev.version_label)
        self.assertEqual(msg.payload["data"]["revision_id"], rev.pk)

    def test_emit_studio_config_published_filters_events(self):
        from delayu.services.studio_publish_events import emit_studio_config_published

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_wh_other",
            name="Other",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/other",
                "events": ["other.event"],
            },
        )
        wh = IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_wh_ok",
            name="Studio",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/ok",
                "events": ["studio.config_published"],
            },
        )
        from delayu.models import StudioConfigRevision

        rev = StudioConfigRevision.objects.create(
            subsystem=self.sub,
            version_label="v9",
            snapshot={},
            published_by=self.user,
        )
        count = emit_studio_config_published(self.sub, rev, self.user, comment="x")
        self.assertEqual(count, 1)
        from delayu.models import IntegrationMessage

        self.assertTrue(IntegrationMessage.objects.filter(endpoint=wh).exists())

    def test_seed_studio_templates_command(self):
        from io import StringIO

        from django.core.management import call_command

        from delayu.models_business import NotificationTemplate

        NotificationTemplate.objects.filter(
            subsystem=self.sub, event_code="studio_scheduled_publish"
        ).delete()
        out = StringIO()
        call_command("seed_studio_templates", "--subsystem", "test", stdout=out)
        self.assertEqual(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio_scheduled_publish"
            ).count(),
            3,
        )
        self.assertEqual(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.config_published"
            ).count(),
            2,
        )
        self.assertEqual(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.config_restored"
            ).count(),
            3,
        )
        self.assertEqual(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.activity_digest"
            ).count(),
            2,
        )
        self.assertIn("Готово", out.getvalue())

    def test_dry_run_publish(self):
        layout = [{"header": "Новое", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        result = studio_admin.dry_run_publish(self.sub)
        self.assertTrue(result["ok"])
        self.assertIn("menu", result["draft_sections"])
        self.assertTrue(result["has_changes"])
        self.assertIn("diff", result)

    def test_dry_run_publish_no_draft(self):
        result = studio_admin.dry_run_publish(self.sub)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_draft")

    def test_notify_studio_config_published(self):
        from unittest.mock import patch

        from delayu.services.studio_notification_templates import ensure_studio_notification_templates
        from delayu.services.studio_publish_events import on_studio_config_published

        ensure_studio_notification_templates(self.sub)
        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        with patch("delayu.services.notify_dispatch.dispatch_event") as dispatch_mock:
            rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="notify")
            self.assertTrue(dispatch_mock.called)
            codes = [call.args[1] for call in dispatch_mock.call_args_list]
            self.assertIn("studio.config_published", codes)

    def test_export_studio_audit_csv(self):
        from delayu.services.audit import export_studio_audit_csv, log_action

        log_action(
            self.user,
            self.sub,
            "studio.publish",
            "StudioConfigRevision",
            "1",
            payload={"version": "v1"},
        )
        log_action(
            self.user,
            self.sub,
            "platform.login",
            "User",
            str(self.user.pk),
            payload={},
        )
        resp = export_studio_audit_csv(self.sub)
        body = resp.content.decode("utf-8-sig")
        self.assertIn("studio.publish", body)
        self.assertNotIn("platform.login", body)
        self.assertIn("studio-audit-test", resp["Content-Disposition"])

    def test_publish_dry_run_api(self):
        from delayu.models_business import AuditLog
        from delayu.views_studio import StudioPublishDryRunApiView

        layout = [{"header": "Dry", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post("/studio/api/publish/dry-run/", data="{}", content_type="application/json")
        request.user = self.user
        response = StudioPublishDryRunApiView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertTrue(
            AuditLog.objects.filter(subsystem=self.sub, action="studio.dry_run.publish").exists()
        )

    def test_dry_run_publish_policies_drift(self):
        from delayu.services.retention import get_or_create_retention_policy

        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.publish_studio_draft(self.sub, self.user)
        retention = get_or_create_retention_policy(self.sub)
        retention.default_archive_years = 50
        retention.save(update_fields=["default_archive_years"])
        studio_admin.save_draft(self.sub, "menu", layout)
        result = studio_admin.dry_run_publish(self.sub)
        self.assertTrue(result["ok"])
        self.assertTrue(result["policies_drift"])
        self.assertTrue(result["policies_diff"]["changed"])

    def test_dry_run_restore(self):
        from delayu.models import FormSchema

        layout1 = [{"header": "A", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout1)
        rev1 = studio_admin.publish_studio_draft(self.sub, self.user)
        FormSchema.objects.create(
            subsystem=self.sub,
            code="extra",
            name="Extra",
            target="case",
            schema=[{"key": "x", "label": "X", "type": "text"}],
        )
        result = studio_admin.dry_run_restore(self.sub, rev1, mode="apply")
        self.assertTrue(result["ok"])
        self.assertTrue(result["has_changes"])
        self.assertIn("diff", result)

    def test_restore_dry_run_api(self):
        from delayu.models_business import AuditLog
        from delayu.views_studio import StudioRestoreDryRunApiView

        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        studio_admin.save_draft(self.sub, "menu", [{"header": "New", "items": []}])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/restore/dry-run/",
            data=json.dumps({"revision_id": rev.pk, "mode": "draft"}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRestoreDryRunApiView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertTrue(
            AuditLog.objects.filter(subsystem=self.sub, action="studio.dry_run.restore").exists()
        )

    def test_export_studio_audit_filtered_action(self):
        from delayu.services.audit import export_studio_audit_csv, log_action

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={})
        log_action(self.user, self.sub, "studio.import", "X", "2", payload={})
        resp = export_studio_audit_csv(self.sub, action="studio.publish")
        body = resp.content.decode("utf-8-sig")
        self.assertIn("studio.publish", body)
        self.assertNotIn("studio.import", body)

    def test_restore_blocked_without_force(self):
        from delayu.services.studio_import_risk import ImportRiskError

        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="live_ep",
            name="Live",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        with self.assertRaises(ImportRiskError):
            studio_admin.restore_revision(self.sub, rev, self.user, mode="apply", force=False)

    def test_restore_with_force(self):
        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="live_ep",
            name="Live",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        result = studio_admin.restore_revision(
            self.sub, rev, self.user, mode="draft", force=True
        )
        self.assertTrue(result["restore_risk"]["blocked"])

    def test_dry_run_restore_includes_risk(self):
        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="live_ep",
            name="Live",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        result = studio_admin.dry_run_restore(self.sub, rev, mode="apply")
        self.assertIn("risk", result)
        self.assertTrue(result["risk"]["blocked"])

    def test_notify_forced_import(self):
        from delayu.models import Notification
        from delayu.services.studio_forced_import import notify_studio_forced_import
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        admin2 = User.objects.create_user(username="admin2", password="x")
        admin_role = Role.objects.get(subsystem=self.sub, code="admin")
        SubsystemMembership.objects.create(
            user=admin2,
            subsystem=self.sub,
            organization=self.org,
            role=admin_role,
        )
        ensure_studio_notification_templates(self.sub)
        risk = {"blocked": True, "critical": [{"message": "test critical"}]}
        before = Notification.objects.filter(user=admin2, subsystem=self.sub).count()
        count = notify_studio_forced_import(self.sub, self.user, risk, action="import")
        after = Notification.objects.filter(user=admin2, subsystem=self.sub).count()
        self.assertGreaterEqual(count, 1)
        self.assertGreater(after, before)

    def test_import_force_notifies_admins(self):
        from unittest.mock import patch

        from delayu.views_studio import StudioImportConfigApiView

        admin2 = User.objects.create_user(username="admin2b", password="x")
        admin_role = Role.objects.get(subsystem=self.sub, code="admin")
        SubsystemMembership.objects.create(
            user=admin2,
            subsystem=self.sub,
            organization=self.org,
            role=admin_role,
        )
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="risk_ep",
            name="Риск",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["integrations"] = []
        package["force"] = True
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/import/",
            data=json.dumps(package),
            content_type="application/json",
        )
        request.user = self.user
        with patch("delayu.services.studio_forced_import.notify_studio_forced_import") as notify_mock:
            response = StudioImportConfigApiView.as_view()(request)
            self.assertEqual(response.status_code, 200)
            notify_mock.assert_called_once()

    def test_restore_api_blocked_409(self):
        from delayu.views_studio import StudioRestoreRevisionApiView

        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="live_ep",
            name="Live",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/restore/",
            data=json.dumps({"revision_id": rev.pk, "mode": "apply"}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRestoreRevisionApiView.as_view()(request)
        self.assertEqual(response.status_code, 409)

    def test_compare_restore_entity_diffs(self):
        from delayu.models import FormSchema

        FormSchema.objects.create(
            subsystem=self.sub,
            code="case_main",
            name="Дело",
            target="case",
            schema=[{"key": "a", "label": "A", "type": "text"}],
        )
        rev_snap = studio_admin.capture_snapshot(self.sub)
        FormSchema.objects.filter(subsystem=self.sub, code="case_main").update(
            schema=[{"key": "a", "label": "A", "type": "text"}, {"key": "b", "label": "B", "type": "text"}]
        )
        current = studio_admin.effective_snapshot(self.sub)
        result = studio_admin.compare_restore_entity_diffs(current, rev_snap)
        self.assertTrue(result["has_form_changes"])
        self.assertEqual(result["forms"][0]["change"], "modified")

    def test_restore_emits_webhook(self):
        from delayu.models import IntegrationMessage

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="restore_wh",
            name="Restore WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/restore-hook",
                "events": ["studio.config_restored"],
            },
        )
        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        studio_admin.restore_revision(self.sub, rev, self.user, mode="draft")
        msg = IntegrationMessage.objects.filter(endpoint__code="restore_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.config_restored")
        self.assertEqual(msg.payload["data"]["mode"], "draft")

    def test_forced_log_on_hub_context(self):
        from delayu.services.audit import log_action
        from delayu.views_studio import StudioHubView

        log_action(
            self.user,
            self.sub,
            "studio.import",
            "Subsystem",
            self.sub.pk,
            payload={"forced": True, "stats": {"forms": 2}},
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/")
        request.user = self.user
        view = StudioHubView()
        view.setup(request)
        ctx = view.get_context_data()
        self.assertEqual(len(ctx["studio_forced_log"]), 1)
        self.assertTrue(ctx["studio_forced_log"][0].payload.get("forced"))

    def test_compare_snapshots_detailed(self):
        from delayu.models import FormSchema
        from delayu.services.studio_revision_compare import compare_snapshots_detailed

        FormSchema.objects.create(
            subsystem=self.sub,
            code="det_form",
            name="Det",
            target="case",
            schema=[{"key": "x", "label": "X", "type": "text"}],
        )
        before = studio_admin.capture_snapshot(self.sub)
        FormSchema.objects.filter(subsystem=self.sub, code="det_form").update(
            schema=[{"key": "x", "label": "X", "type": "text"}, {"key": "y", "label": "Y", "type": "text"}]
        )
        after = studio_admin.capture_snapshot(self.sub)
        result = compare_snapshots_detailed(before, after)
        self.assertTrue(result["entity_diffs"]["has_form_changes"])
        self.assertIn("policies_diff", result)

    def test_revision_compare_api_entity_diffs(self):
        from delayu.models import FormSchema
        from delayu.models_business import AuditLog
        from delayu.views_studio import StudioRevisionCompareApiView

        FormSchema.objects.create(
            subsystem=self.sub,
            code="api_form",
            name="Api",
            target="case",
            schema=[{"key": "f", "label": "F", "type": "text"}],
        )
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        FormSchema.objects.filter(subsystem=self.sub, code="api_form").delete()
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get(f"/studio/api/revisions/compare/?a={rev.pk}&b=live")
        request.user = self.user
        response = StudioRevisionCompareApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["entity_diffs"]["has_form_changes"])
        self.assertTrue(
            AuditLog.objects.filter(subsystem=self.sub, action="studio.compare_revisions").exists()
        )

    def test_export_studio_forced_audit_csv(self):
        from delayu.services.audit import export_studio_forced_audit_csv, log_action

        log_action(
            self.user,
            self.sub,
            "studio.restore",
            "Subsystem",
            self.sub.pk,
            payload={"forced": True, "from": "1.0.0"},
        )
        log_action(self.user, self.sub, "studio.publish", "Subsystem", self.sub.pk, payload={})
        resp = export_studio_forced_audit_csv(self.sub)
        body = resp.content.decode("utf-8-sig")
        self.assertIn("studio.restore", body)
        self.assertNotIn("studio.publish", body)
        self.assertIn("forced", body.lower())

    def test_export_studio_compliance_package(self):
        import zipfile
        from io import BytesIO

        from delayu.services.audit import export_studio_compliance_package

        resp = export_studio_compliance_package(self.sub)
        self.assertEqual(resp["Content-Type"], "application/zip")
        with zipfile.ZipFile(BytesIO(resp.content)) as zf:
            names = zf.namelist()
            self.assertIn("config.json", names)
            self.assertIn("studio-audit.csv", names)
            self.assertIn("manifest.json", names)
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest["format"], "delayu-studio-compliance")
            self.assertEqual(manifest["format_version"], 4)
            self.assertIn("studio-forced-audit.csv", names)
            self.assertIn("revisions.json", names)
            self.assertIn("studio-activity.csv", names)
            self.assertIn("revision-meta.json", names)

    def test_notify_studio_config_restored(self):
        from unittest.mock import patch

        from delayu.models_business import NotificationTemplate
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates
        from delayu.services.studio_publish_events import notify_studio_config_restored

        ensure_studio_notification_templates(self.sub)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        with patch("delayu.services.notify_dispatch.dispatch_event") as mock_dispatch:
            notify_studio_config_restored(
                self.sub, rev, self.user, mode="draft", from_version=rev.version_label
            )
        self.assertTrue(mock_dispatch.called)
        self.assertTrue(
            NotificationTemplate.objects.filter(
                subsystem=self.sub, event_code="studio.config_restored"
            ).exists()
        )

    def test_hub_studio_stats_and_health_urls(self):
        from delayu.views_studio import StudioHubView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/")
        request.user = self.user
        view = StudioHubView()
        view.setup(request)
        ctx = view.get_context_data()
        self.assertIn("revisions", ctx["studio_stats"])
        self.assertIn("forced_ops", ctx["studio_stats"])
        self.assertTrue(any(c.get("url") for c in ctx["studio_health_checks"]))

    def test_audit_export_forced_filter(self):
        from delayu.services.audit import export_studio_audit_csv, log_action

        log_action(
            self.user,
            self.sub,
            "studio.import",
            "Subsystem",
            self.sub.pk,
            payload={"forced": True},
        )
        log_action(self.user, self.sub, "studio.publish", "Subsystem", self.sub.pk, payload={})
        resp = export_studio_audit_csv(self.sub, forced_only=True)
        body = resp.content.decode("utf-8-sig")
        self.assertIn("studio.import", body)
        self.assertNotIn("studio.publish", body)

    def test_dry_run_import_entity_diffs(self):
        from delayu.models import FormSchema

        FormSchema.objects.create(
            subsystem=self.sub,
            code="imp_form",
            name="Imp",
            target="case",
            schema=[{"key": "a", "label": "A", "type": "text"}],
        )
        package = studio_admin.export_config_package(self.sub)
        package["snapshot"]["forms"] = []
        result = studio_admin.dry_run_import_package(self.sub, package)
        self.assertTrue(result["ok"])
        self.assertTrue(result["entity_diffs"]["has_form_changes"])

    def test_export_revision_package(self):
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        pkg = studio_admin.export_revision_package(rev)
        self.assertEqual(pkg["format"], "delayu-studio-revision")
        self.assertEqual(pkg["version_label"], rev.version_label)
        self.assertIn("snapshot", pkg)

    def test_studio_summary_api(self):
        from delayu.views_studio import StudioSummaryApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/summary/")
        request.user = self.user
        response = StudioSummaryApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertIn("health", data)
        self.assertIn("revisions", data)

    def test_revision_export_view(self):
        from delayu.views_studio import StudioRevisionExportView

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get(f"/studio/api/revisions/{rev.pk}/export/")
        request.user = self.user
        response = StudioRevisionExportView.as_view()(request, revision_id=rev.pk)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["revision_id"], rev.pk)

    def test_revision_compare_export_csv(self):
        from delayu.services.audit import export_revision_compare_csv
        from delayu.services.studio_revision_compare import compare_snapshots_detailed

        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        before = studio_admin.capture_snapshot(self.sub)
        after = dict(before)
        after["menu_layout"] = [{"header": "Y", "items": ["platform-home", "platform-cases"]}]
        result = compare_snapshots_detailed(before, after)
        resp = export_revision_compare_csv(self.sub, result, rev_a="live", rev_b="draft")
        body = resp.content.decode("utf-8-sig")
        self.assertIn("menu_layout", body)

    def test_forced_restore_notifies_via_event_handler(self):
        from unittest.mock import patch

        layout = [{"header": "Old", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="live_ep_notify",
            name="Live",
            endpoint_type=IntegrationEndpoint.EndpointType.SMEV,
            config={},
        )
        with patch("delayu.services.studio_forced_import.notify_studio_forced_import") as notify_mock:
            studio_admin.restore_revision(self.sub, rev, self.user, mode="draft", force=True)
        self.assertTrue(notify_mock.called)

    def test_dry_run_blueprint_detailed(self):
        result = studio_admin.dry_run_blueprint(self.sub, "operator_daily")
        self.assertTrue(result["ok"])
        self.assertIn("entity_diffs", result)
        self.assertIn("has_detail_changes", result)

    def test_prune_studio_revisions(self):
        from delayu.models import StudioConfigRevision

        for i in range(3):
            layout = [{"header": f"H{i}", "items": ["platform-home"]}]
            studio_admin.save_draft(self.sub, "menu", layout)
            studio_admin.publish_studio_draft(self.sub, self.user, comment=f"rev {i}")
        self.assertEqual(StudioConfigRevision.objects.filter(subsystem=self.sub).count(), 3)
        result = studio_admin.prune_studio_revisions(self.sub, keep=1, dry_run=True)
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["would_delete"], 2)
        studio_admin.prune_studio_revisions(self.sub, keep=1, dry_run=False)
        self.assertEqual(StudioConfigRevision.objects.filter(subsystem=self.sub).count(), 1)

    def test_pin_revision_survives_prune(self):
        from delayu.models import StudioConfigRevision

        revs = []
        for i in range(4):
            revs.append(studio_admin.publish_studio_draft(self.sub, self.user, comment=f"p{i}"))
        pinned = revs[0]
        studio_admin.set_revision_pinned(self.sub, pinned.pk, pinned=True)
        studio_admin.prune_studio_revisions(self.sub, keep=1, dry_run=False)
        self.assertTrue(StudioConfigRevision.objects.filter(pk=pinned.pk).exists())

    def test_studio_activity_digest(self):
        from delayu.services.audit import log_action
        from delayu.services.studio_activity import build_studio_activity_digest

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        digest = build_studio_activity_digest(self.sub, days=7)
        self.assertTrue(digest["ok"])
        self.assertGreaterEqual(digest["total"], 1)

    def test_preview_schedule_publish(self):
        from delayu.services.studio_publish_schedule import preview_schedule_publish
        from django.utils import timezone
        from datetime import timedelta

        layout = [{"header": "Sched", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        at = timezone.now() + timedelta(hours=2)
        result = preview_schedule_publish(self.sub, at, comment="test")
        self.assertTrue(result["ok"])
        self.assertTrue(result["schedule_preview"])
        self.assertIn("scheduled_at", result)

    def test_notify_studio_activity_digest(self):
        from unittest.mock import patch

        from delayu.services.audit import log_action
        from delayu.services.studio_activity import notify_studio_activity_digest_admins
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        ensure_studio_notification_templates(self.sub)
        with patch("delayu.services.notify_dispatch.dispatch_event") as dispatch_mock:
            count = notify_studio_activity_digest_admins(self.sub, days=7)
            self.assertGreaterEqual(count, 1)
            self.assertTrue(dispatch_mock.called)
            self.assertEqual(dispatch_mock.call_args[0][1], "studio.activity_digest")

    def test_notify_studio_activity_digest_no_events(self):
        from delayu.services.studio_activity import notify_studio_activity_digest_admins

        self.assertEqual(notify_studio_activity_digest_admins(self.sub, days=7), 0)

    def test_list_studio_revisions_pinned_first(self):
        from delayu.models import StudioConfigRevision

        revs = []
        for i in range(3):
            revs.append(studio_admin.publish_studio_draft(self.sub, self.user, comment=f"r{i}"))
        studio_admin.set_revision_pinned(self.sub, revs[0].pk, pinned=True)
        data = studio_admin.list_studio_revisions(self.sub, limit=10)
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"][0]["id"], revs[0].pk)
        self.assertTrue(data["items"][0]["pinned"])

    def test_compare_blueprint_with_revision(self):
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="bp base")
        result = studio_admin.compare_blueprint_with_revision(
            self.sub, "operator_daily", rev.pk
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["revision_id"], rev.pk)
        self.assertIn("diff", result)

    def test_export_revisions_archive(self):
        import io
        import json
        import zipfile

        studio_admin.publish_studio_draft(self.sub, self.user, comment="zip test")
        resp = studio_admin.export_revisions_archive(self.sub)
        self.assertEqual(resp.status_code, 200)
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        self.assertIn("manifest.json", names)
        manifest = json.loads(zf.read("manifest.json"))
        self.assertEqual(manifest["format"], "delayu-studio-revisions-archive")
        self.assertEqual(manifest["format_version"], 3)
        self.assertIn("revision-meta.json", names)
        self.assertGreaterEqual(manifest["count"], 1)

    def test_studio_summary_pinned_and_activity(self):
        from delayu.services.audit import log_action

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        studio_admin.set_revision_pinned(self.sub, rev.pk, pinned=True)
        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        summary = studio_admin.studio_summary(self.sub)
        self.assertGreaterEqual(summary["pinned_revisions"], 1)
        self.assertGreaterEqual(summary["activity_7d"], 1)

    def test_activity_notify_api(self):
        from delayu.services.audit import log_action
        from delayu.views_studio import StudioActivityNotifyView

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/activity/notify/",
            data=json.dumps({"days": 7}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioActivityNotifyView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["notified"], 1)

    def test_revisions_list_api(self):
        from delayu.views_studio import StudioRevisionsListApiView

        studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/revisions/")
        request.user = self.user
        response = StudioRevisionsListApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["total"], 1)
        self.assertGreaterEqual(len(data["items"]), 1)

    def test_revisions_bulk_export_view(self):
        from delayu.views_studio import StudioRevisionsBulkExportView

        studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/revisions/export.zip")
        request.user = self.user
        response = StudioRevisionsBulkExportView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/zip", response["Content-Type"])

    def test_blueprint_compare_api(self):
        from delayu.views_studio import StudioBlueprintCompareApiView

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get(
            f"/studio/api/blueprints/compare/?blueprint_id=operator_daily&revision_id={rev.pk}"
        )
        request.user = self.user
        response = StudioBlueprintCompareApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["revision_id"], rev.pk)

    def test_compare_blueprint_with_live(self):
        result = studio_admin.compare_blueprint_with_live(self.sub, "operator_daily")
        self.assertTrue(result["ok"])
        self.assertEqual(result["compare_with"], "live")
        self.assertIn("diff", result)

    def test_compare_blueprint_package_with_revision(self):
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="pkg base")
        package = studio_admin.get_blueprint_package("operator_daily")
        result = studio_admin.compare_blueprint_package_with_revision(
            self.sub, package, rev.pk
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["revision_id"], rev.pk)
        self.assertIn("diff", result)

    def test_activity_digest_schedule(self):
        from delayu.services.studio_activity_schedule import (
            get_activity_digest_schedule,
            process_due_studio_activity_digests,
            set_activity_digest_schedule,
        )

        sched = set_activity_digest_schedule(
            self.sub, enabled=True, interval_days=7, digest_days=7
        )
        self.assertTrue(sched["enabled"])
        self.assertEqual(sched["interval_days"], 7)
        loaded = get_activity_digest_schedule(self.sub)
        self.assertTrue(loaded["enabled"])
        result = process_due_studio_activity_digests(limit=5)
        self.assertIn("count", result)

    def test_process_due_activity_digest_sends(self):
        from datetime import timedelta
        from unittest.mock import patch

        from django.utils import timezone

        from delayu.services.audit import log_action
        from delayu.services.studio_activity_schedule import (
            process_due_studio_activity_digests,
            set_activity_digest_schedule,
        )
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        ensure_studio_notification_templates(self.sub)
        set_activity_digest_schedule(self.sub, enabled=True, interval_days=1, digest_days=7)
        state = dict(self.sub.studio_setup_state or {})
        entry = dict(state.get("activity_digest_schedule") or {})
        entry["last_sent_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        state["activity_digest_schedule"] = entry
        self.sub.studio_setup_state = state
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        with patch("delayu.services.notify_dispatch.dispatch_event") as dispatch_mock:
            result = process_due_studio_activity_digests(limit=5)
            self.assertGreaterEqual(result["count"], 1)
            self.assertTrue(dispatch_mock.called)

    def test_activity_schedule_api(self):
        from delayu.views_studio import StudioActivityScheduleApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/activity/schedule/",
            data=json.dumps({"enabled": True, "interval_days": 14, "digest_days": 7}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioActivityScheduleApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertTrue(data["schedule"]["enabled"])
        self.assertEqual(data["schedule"]["interval_days"], 14)

    def test_blueprint_compare_live_api(self):
        from delayu.views_studio import StudioBlueprintCompareLiveApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/blueprints/compare/live/?blueprint_id=operator_daily")
        request.user = self.user
        response = StudioBlueprintCompareLiveApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["compare_with"], "live")

    def test_prune_emits_webhook(self):
        from delayu.models import IntegrationMessage, StudioConfigRevision

        for i in range(8):
            studio_admin.publish_studio_draft(self.sub, self.user, comment=f"p{i}")
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_prune_wh",
            name="Prune WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/prune-hook",
                "events": ["studio.revisions_pruned"],
            },
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/prune/",
            data=json.dumps({"keep": 3, "dry_run": False}),
            content_type="application/json",
        )
        request.user = self.user
        from delayu.views_studio import StudioRevisionPruneApiView

        response = StudioRevisionPruneApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertGreater(data.get("deleted", 0), 0)
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_prune_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.revisions_pruned")

    def test_studio_summary_activity_digest_fields(self):
        from delayu.services.studio_activity_schedule import set_activity_digest_schedule

        set_activity_digest_schedule(self.sub, enabled=True, interval_days=14)
        summary = studio_admin.studio_summary(self.sub)
        self.assertTrue(summary["activity_digest_enabled"])
        self.assertEqual(summary["activity_digest_interval_days"], 14)

    def test_update_revision_meta(self):
        rev = studio_admin.publish_studio_draft(self.sub, self.user, comment="old")
        result = studio_admin.update_revision_meta(
            self.sub, rev.pk, comment="new comment", tags=["prod", "release"]
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["comment"], "new comment")
        self.assertEqual(result["tags"], ["prod", "release"])
        rev.refresh_from_db()
        self.assertEqual(rev.comment, "new comment")
        listed = studio_admin.list_studio_revisions(self.sub, limit=5)
        item = next(i for i in listed["items"] if i["id"] == rev.pk)
        self.assertEqual(item["tags"], ["prod", "release"])

    def test_revision_meta_api(self):
        from delayu.views_studio import StudioRevisionMetaApiView

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/meta/",
            data=json.dumps(
                {"revision_id": rev.pk, "comment": "via api", "tags": ["test"]}
            ),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRevisionMetaApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["comment"], "via api")
        self.assertEqual(data["tags"], ["test"])

    def test_compare_blueprint_package_with_live(self):
        package = studio_admin.get_blueprint_package("operator_daily")
        result = studio_admin.compare_blueprint_package_with_live(self.sub, package)
        self.assertTrue(result["ok"])
        self.assertEqual(result["compare_with"], "live")
        self.assertIn("diff", result)

    def test_activity_digest_webhook(self):
        from unittest.mock import patch

        from delayu.models import IntegrationMessage
        from delayu.services.audit import log_action
        from delayu.services.studio_activity import notify_studio_activity_digest_admins
        from delayu.services.studio_notification_templates import ensure_studio_notification_templates

        log_action(self.user, self.sub, "studio.publish", "X", "1", payload={"version": "1.0.0"})
        ensure_studio_notification_templates(self.sub)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_digest_wh",
            name="Digest WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/digest-hook",
                "events": ["studio.activity_digest"],
            },
        )
        with patch("delayu.services.notify_dispatch.dispatch_event"):
            notify_studio_activity_digest_admins(self.sub, days=7)
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_digest_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.activity_digest")

    def test_compliance_export_schedule(self):
        from delayu.services.studio_compliance_schedule import (
            get_compliance_export_schedule,
            process_due_studio_compliance_exports,
            save_studio_compliance_snapshot,
            set_compliance_export_schedule,
        )

        sched = set_compliance_export_schedule(
            self.sub, enabled=True, interval_days=30, mask_pii=False
        )
        self.assertTrue(sched["enabled"])
        snapshot = save_studio_compliance_snapshot(self.sub)
        self.assertTrue(snapshot["filename"].endswith(".zip"))
        loaded = get_compliance_export_schedule(self.sub)
        self.assertTrue(loaded["enabled"])
        result = process_due_studio_compliance_exports(limit=5)
        self.assertIn("count", result)

    def test_process_due_compliance_export(self):
        from datetime import timedelta

        from django.utils import timezone

        from delayu.services.studio_compliance_schedule import (
            process_due_studio_compliance_exports,
            set_compliance_export_schedule,
        )

        set_compliance_export_schedule(self.sub, enabled=True, interval_days=1)
        state = dict(self.sub.studio_setup_state or {})
        entry = dict(state.get("compliance_export_schedule") or {})
        entry["last_export_at"] = (timezone.now() - timedelta(days=2)).isoformat()
        state["compliance_export_schedule"] = entry
        self.sub.studio_setup_state = state
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        result = process_due_studio_compliance_exports(limit=5)
        self.assertGreaterEqual(result["count"], 1)
        self.assertTrue(result["exported"][0]["filename"].endswith(".zip"))

    def test_compliance_schedule_api(self):
        from delayu.views_studio import StudioComplianceScheduleApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/compliance/schedule/",
            data=json.dumps({"enabled": True, "interval_days": 14, "mask_pii": False}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioComplianceScheduleApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertTrue(data["schedule"]["enabled"])
        self.assertEqual(data["schedule"]["interval_days"], 14)

    def test_blueprint_package_compare_live_api(self):
        from delayu.views_studio import StudioBlueprintPackageCompareLiveApiView

        package = studio_admin.get_blueprint_package("operator_daily")
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/blueprints/compare/package/live/",
            data=json.dumps({"package": package}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioBlueprintPackageCompareLiveApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["compare_with"], "live")

    def test_publish_with_tags(self):
        layout = [{"header": "T", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        rev = studio_admin.publish_studio_draft(
            self.sub, self.user, comment="tagged", tags=["prod", "v1"]
        )
        tags = studio_admin.get_revision_tags_map(self.sub).get(rev.pk, [])
        self.assertEqual(tags, ["prod", "v1"])

    def test_list_studio_revisions_filter_by_tag(self):
        rev1 = studio_admin.publish_studio_draft(self.sub, self.user, tags=["prod"])
        studio_admin.publish_studio_draft(self.sub, self.user, tags=["dev"])
        data = studio_admin.list_studio_revisions(self.sub, tag="prod", limit=10)
        self.assertTrue(data["ok"])
        ids = [item["id"] for item in data["items"]]
        self.assertIn(rev1.pk, ids)
        self.assertTrue(all("prod" in item["tags"] for item in data["items"]))

    def test_list_revision_tags(self):
        studio_admin.publish_studio_draft(self.sub, self.user, tags=["Beta", "prod"])
        studio_admin.publish_studio_draft(self.sub, self.user, tags=["prod"])
        tags = studio_admin.list_revision_tags(self.sub)
        self.assertIn("prod", tags)
        self.assertIn("Beta", tags)

    def test_revision_tags_api(self):
        from delayu.views_studio import StudioRevisionTagsApiView

        studio_admin.publish_studio_draft(self.sub, self.user, tags=["release"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/revisions/tags/")
        request.user = self.user
        response = StudioRevisionTagsApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertIn("release", data["tags"])

    def test_compliance_export_webhook(self):
        from delayu.models import IntegrationMessage
        from delayu.views_studio import StudioComplianceExportView

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_compliance_wh",
            name="Compliance WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/compliance-hook",
                "events": ["studio.compliance_export"],
            },
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.get("/studio/api/compliance/export.zip")
        request.user = self.user
        response = StudioComplianceExportView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_compliance_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.compliance_export")
        self.assertEqual(msg.payload["data"]["source"], "manual")

    def test_publish_api_with_tags(self):
        from delayu.views_studio import StudioPublishApiView

        layout = [{"header": "API", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/publish/",
            data=json.dumps({"comment": "api tags", "tags": ["hotfix"]}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioPublishApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tags"], ["hotfix"])

    def test_bulk_set_revision_tags(self):
        rev1 = studio_admin.publish_studio_draft(self.sub, self.user)
        rev2 = studio_admin.publish_studio_draft(self.sub, self.user)
        result = studio_admin.bulk_set_revision_tags(
            self.sub, [rev1.pk, rev2.pk], ["release"], mode="add"
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        tags = studio_admin.get_revision_tags_map(self.sub)
        self.assertEqual(tags.get(rev1.pk), ["release"])

    def test_filter_studio_audit_by_revision_tag(self):
        from delayu.models_business import AuditLog
        from delayu.services.audit import log_action

        rev = studio_admin.publish_studio_draft(self.sub, self.user, tags=["audit-tag"])
        log_action(
            self.user,
            self.sub,
            "studio.publish",
            "StudioConfigRevision",
            rev.pk,
            payload={"version": rev.version_label},
        )
        qs = AuditLog.objects.filter(subsystem=self.sub, action__startswith="studio.")
        filtered = studio_admin.filter_studio_audit_by_revision_tag(
            qs, self.sub, "audit-tag"
        )
        self.assertGreaterEqual(filtered.count(), 1)

    def test_revision_meta_webhook(self):
        from delayu.models import IntegrationMessage
        from delayu.views_studio import StudioRevisionMetaApiView

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_meta_wh",
            name="Meta WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/meta-hook",
                "events": ["studio.revision_meta"],
            },
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/meta/",
            data=json.dumps(
                {"revision_id": rev.pk, "comment": "wh", "tags": ["notified"]}
            ),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRevisionMetaApiView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_meta_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.revision_meta")

    def test_export_revisions_archive_by_tag(self):
        import io
        import json
        import zipfile

        rev = studio_admin.publish_studio_draft(self.sub, self.user, tags=["export-only"])
        studio_admin.publish_studio_draft(self.sub, self.user, tags=["other"])
        resp = studio_admin.export_revisions_archive(self.sub, tag="export-only")
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        manifest = json.loads(zf.read("manifest.json"))
        self.assertEqual(manifest["tag_filter"], "export-only")
        self.assertEqual(manifest["count"], 1)
        self.assertEqual(manifest["revisions"][0]["id"], rev.pk)

    def test_revision_bulk_tags_api(self):
        from delayu.views_studio import StudioRevisionBulkTagsApiView

        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/tags/bulk/",
            data=json.dumps(
                {"revision_ids": [rev.pk], "tags": ["bulk"], "mode": "set"}
            ),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRevisionBulkTagsApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["count"], 1)

    def test_default_publish_tags(self):
        studio_admin.set_default_publish_tags(self.sub, ["prod", "release"])
        merged = studio_admin.merge_publish_tags(self.sub, ["hotfix"])
        self.assertEqual(merged, ["hotfix", "prod", "release"])

    def test_publish_merges_default_and_pending_tags(self):
        layout = [{"header": "M", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.set_default_publish_tags(self.sub, ["prod"])
        studio_admin.set_pending_publish_tags(self.sub, ["blueprint"])
        rev = studio_admin.publish_studio_draft(self.sub, self.user, tags=["release"])
        tags = studio_admin.get_revision_tags_map(self.sub).get(rev.pk, [])
        self.assertEqual(tags, ["release", "blueprint", "prod"])
        self.assertEqual(studio_admin.get_pending_publish_tags(self.sub), [])

    def test_apply_blueprint_queues_publish_tags(self):
        result = studio_admin.apply_blueprint(self.sub, "operator_daily")
        self.assertIn("pending_publish_tags", result)
        self.assertIn("operator_daily", studio_admin.get_pending_publish_tags(self.sub))

    def test_list_studio_revisions_search(self):
        rev = studio_admin.publish_studio_draft(
            self.sub, self.user, comment="release candidate", tags=["rc1"]
        )
        data = studio_admin.list_studio_revisions(self.sub, q="candidate", limit=10)
        self.assertTrue(data["ok"])
        self.assertEqual(data["items"][0]["id"], rev.pk)

    def test_export_revisions_pinned_only(self):
        import io
        import json
        import zipfile

        revs = []
        for i in range(3):
            revs.append(studio_admin.publish_studio_draft(self.sub, self.user, comment=f"p{i}"))
        studio_admin.set_revision_pinned(self.sub, revs[0].pk, pinned=True)
        resp = studio_admin.export_revisions_archive(self.sub, pinned_only=True)
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        manifest = json.loads(zf.read("manifest.json"))
        self.assertTrue(manifest["pinned_only"])
        self.assertEqual(manifest["count"], 1)
        self.assertEqual(manifest["revisions"][0]["id"], revs[0].pk)

    def test_default_publish_tags_api(self):
        from delayu.views_studio import StudioDefaultPublishTagsApiView

        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/publish/default-tags/",
            data=json.dumps({"tags": ["prod", "staging"]}),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioDefaultPublishTagsApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["tags"], ["prod", "staging"])

    def test_dry_run_publish_tags_preview(self):
        layout = [{"header": "T", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.set_default_publish_tags(self.sub, ["prod"])
        studio_admin.set_pending_publish_tags(self.sub, ["blueprint"])
        result = studio_admin.dry_run_publish(self.sub, tags=["release"])
        self.assertTrue(result["ok"])
        self.assertEqual(result["publish_tags"], ["release", "blueprint", "prod"])
        self.assertEqual(result["publish_tags_breakdown"]["explicit"], ["release"])
        self.assertEqual(result["publish_tags_breakdown"]["pending"], ["blueprint"])
        self.assertEqual(result["publish_tags_breakdown"]["default"], ["prod"])

    def test_clear_pending_publish_tags_api(self):
        from delayu.views_studio import StudioClearPendingPublishTagsApiView

        studio_admin.set_pending_publish_tags(self.sub, ["bp1", "bp2"])
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/publish/pending-tags/clear/",
            data="{}",
            content_type="application/json",
        )
        request.user = self.user
        response = StudioClearPendingPublishTagsApiView.as_view()(request)
        data = json.loads(response.content)
        self.assertTrue(data["ok"])
        self.assertEqual(data["cleared"], ["bp1", "bp2"])
        self.sub.refresh_from_db()
        self.assertEqual(studio_admin.get_pending_publish_tags(self.sub), [])

    def test_export_studio_compliance_package_by_tag(self):
        import zipfile
        from io import BytesIO

        from delayu.services.audit import export_studio_compliance_package

        rev = studio_admin.publish_studio_draft(self.sub, self.user, tags=["compliance-only"])
        studio_admin.publish_studio_draft(self.sub, self.user, tags=["other"])
        resp = export_studio_compliance_package(self.sub, revision_tag="compliance-only")
        with zipfile.ZipFile(BytesIO(resp.content)) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            revisions = json.loads(zf.read("revisions.json"))
        self.assertEqual(manifest["revision_tag_filter"], "compliance-only")
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0]["id"], rev.pk)

    def test_compliance_schedule_revision_tag(self):
        from delayu.services.studio_compliance_schedule import (
            get_compliance_export_schedule,
            set_compliance_export_schedule,
        )

        sched = set_compliance_export_schedule(
            self.sub, enabled=True, interval_days=14, revision_tag="prod"
        )
        self.assertEqual(sched["revision_tag"], "prod")
        loaded = get_compliance_export_schedule(self.sub)
        self.assertEqual(loaded["revision_tag"], "prod")

    def test_preview_schedule_publish_tags(self):
        from datetime import timedelta

        from django.utils import timezone

        from delayu.services.studio_publish_schedule import preview_schedule_publish

        layout = [{"header": "Sched", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.set_default_publish_tags(self.sub, ["prod"])
        studio_admin.set_pending_publish_tags(self.sub, ["blueprint"])
        at = timezone.now() + timedelta(hours=2)
        result = preview_schedule_publish(self.sub, at, tags=["release"])
        self.assertTrue(result["schedule_preview"])
        self.assertEqual(result["schedule_publish_tags"], ["release", "blueprint", "prod"])
        self.assertEqual(result["publish_tags"], ["release", "blueprint", "prod"])

    def test_scheduled_publish_with_tags(self):
        from datetime import timedelta

        from django.utils import timezone

        from delayu.services.studio_publish_schedule import (
            get_scheduled_publish,
            process_due_scheduled_publishes,
            set_scheduled_publish,
        )

        layout = [{"header": "X", "items": ["platform-home"]}]
        studio_admin.save_draft(self.sub, "menu", layout)
        studio_admin.set_default_publish_tags(self.sub, ["prod"])
        future = timezone.now() + timedelta(hours=2)
        set_scheduled_publish(self.sub, future, comment="tags", user_id=self.user.pk, tags=["release"])
        sched = get_scheduled_publish(self.sub)
        self.assertEqual(sched["tags"], ["release"])
        past_at = (timezone.now() - timedelta(minutes=1)).isoformat()
        state = dict(self.sub.studio_setup_state or {})
        state["scheduled_publish"] = {
            "at": past_at,
            "comment": "сейчас",
            "user_id": self.user.pk,
            "tags": ["release"],
        }
        self.sub.studio_setup_state = state
        self.sub.save(update_fields=["studio_setup_state", "updated_at"])
        process_due_scheduled_publishes()
        self.sub.refresh_from_db()
        rev = self.sub.studio_revisions.order_by("-pk").first()
        tags = studio_admin.get_revision_tags_map(self.sub).get(rev.pk, [])
        self.assertEqual(tags, ["release", "prod"])

    def test_bulk_tags_webhook(self):
        from delayu.models_business import IntegrationEndpoint, IntegrationMessage
        from delayu.views_studio import StudioRevisionBulkTagsApiView

        IntegrationEndpoint.objects.create(
            subsystem=self.sub,
            code="studio_bulk_wh",
            name="Bulk WH",
            endpoint_type=IntegrationEndpoint.EndpointType.WEBHOOK,
            is_active=True,
            config={
                "webhook_url": "https://example.com/bulk-hook",
                "events": ["studio.revision_tags_bulk"],
            },
        )
        rev = studio_admin.publish_studio_draft(self.sub, self.user)
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        rf = RequestFactory()
        request = rf.post(
            "/studio/api/revisions/tags/bulk/",
            data=json.dumps(
                {"revision_ids": [rev.pk], "tags": ["bulk-wh"], "mode": "set"}
            ),
            content_type="application/json",
        )
        request.user = self.user
        response = StudioRevisionBulkTagsApiView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        msg = IntegrationMessage.objects.filter(endpoint__code="studio_bulk_wh").first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.payload["event"], "studio.revision_tags_bulk")

    def test_list_publish_tag_suggestions(self):
        studio_admin.set_default_publish_tags(self.sub, ["prod"])
        studio_admin.set_pending_publish_tags(self.sub, ["blueprint"])
        rev = studio_admin.publish_studio_draft(self.sub, self.user, tags=["rc1"])
        suggestions = studio_admin.list_publish_tag_suggestions(self.sub)
        self.assertIn("prod", suggestions)
        self.assertIn("blueprint", suggestions)
        self.assertIn("rc1", suggestions)
