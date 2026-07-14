"""Document completeness (AI-P0-05)."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from delayu.models import Subsystem
from delayu.models_uzhv import HousingCaseAttachment, HousingCitizen, HousingQueueCase
from delayu.services.document_completeness import (
    DEFAULT_UZHV_REQUIRED,
    housing_case_completeness,
    required_uzhv_doc_kinds,
)

User = get_user_model()


class DocumentCompletenessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="compl_user", password="x")
        self.sub = Subsystem.objects.create(code="t-compl", name="Test")
        self.citizen = HousingCitizen.objects.create(
            subsystem=self.sub,
            last_name="Test",
            first_name="User",
        )

    def test_low_income_missing_docs(self):
        case = HousingQueueCase.objects.create(
            subsystem=self.sub,
            citizen=self.citizen,
            case_number="T-001",
            category=HousingQueueCase.Category.LOW_INCOME,
        )
        HousingCaseAttachment.objects.create(
            case=case,
            title="Заявление",
            doc_kind=HousingCaseAttachment.DocKind.APPLICATION,
            uploaded_by=self.user,
        )
        result = housing_case_completeness(case)
        self.assertFalse(result["complete"])
        self.assertIn("Справка о доходах", result["summary"])
        self.assertEqual(len(result["missing"]), 3)

    def test_low_income_full_pack(self):
        case = HousingQueueCase.objects.create(
            subsystem=self.sub,
            citizen=self.citizen,
            case_number="T-002",
            category=HousingQueueCase.Category.LOW_INCOME,
        )
        for doc_kind, _ in DEFAULT_UZHV_REQUIRED[HousingQueueCase.Category.LOW_INCOME]:
            HousingCaseAttachment.objects.create(
                case=case,
                title=doc_kind,
                doc_kind=doc_kind,
                uploaded_by=self.user,
            )
        result = housing_case_completeness(case)
        self.assertTrue(result["complete"])
        self.assertEqual(result["score"], 1.0)

    def test_required_kinds_default(self):
        kinds = required_uzhv_doc_kinds(self.sub, HousingQueueCase.Category.LOW_INCOME)
        self.assertEqual(len(kinds), 4)
