"""AI P0 features: classify, draft, risks, ai_enabled."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_uzhv import HousingAppeal, HousingCitizen
from delayu.services.ai import classify_correspondence, draft_appeal_response, is_ai_enabled

User = get_user_model()


class ClassifyCorrespondenceTests(TestCase):
    def test_uzhv_low_income_theme(self):
        r = classify_correspondence("Заявление о признании малоимущими", "доход семьи")
        self.assertEqual(r["theme"], "Малоимущие")
        self.assertIn("department", r)
        self.assertGreaterEqual(r["confidence"], 0.7)

    def test_complaint_theme(self):
        r = classify_correspondence("Жалоба на срок рассмотрения", "")
        self.assertEqual(r["theme"], "Жалоба")
        self.assertEqual(r["assignee_role"], "uzhv_queue_spec")


class AiEnabledTests(TestCase):
    def test_default_enabled(self):
        sub = Subsystem.objects.create(code="ai-t", name="T")
        self.assertTrue(is_ai_enabled(sub))

    def test_disabled_policy(self):
        from delayu.services.ai import get_or_create_policy

        sub = Subsystem.objects.create(code="ai-off", name="Off")
        policy = get_or_create_policy(sub)
        policy.ai_enabled = False
        policy.save(update_fields=["ai_enabled"])
        self.assertFalse(is_ai_enabled(sub))


class DraftAppealTests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(code="draft-t", name="T")
        self.user = User.objects.create_user(username="draft_u", password="x")
        self.citizen = HousingCitizen.objects.create(
            subsystem=self.sub, last_name="Иванов", first_name="Иван"
        )

    def test_draft_contains_number(self):
        appeal = HousingAppeal.objects.create(
            subsystem=self.sub,
            appeal_number="ОБ-2026-001",
            subject="Жалоба на задержку",
            body="Прошу ответить",
            due_date=timezone.now().date(),
            created_by=self.user,
            citizen=self.citizen,
        )
        result = draft_appeal_response(appeal)
        self.assertIn("ОБ-2026-001", result["draft"])
        self.assertIn("Иванов", result["draft"])


class AiRisksDashboardTests(TestCase):
    def setUp(self):
        self.sub = Subsystem.objects.create(code="risk-t", name="T", industry_template="uzhv")
        self.user = User.objects.create_user(username="risk_u", password="x")

    def test_ai_risk_dashboard_empty(self):
        from delayu.services.analytics import ai_risk_dashboard

        data = ai_risk_dashboard(self.sub)
        self.assertEqual(data["summary"]["appeals_overdue"], 0)
        self.assertIn("heatmap", data)
