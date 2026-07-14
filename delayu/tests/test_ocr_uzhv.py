"""OCR + NER (AI-P0-03, AI-P0-04)."""
import json

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from delayu.models import UserProfile
from delayu.models_uzhv import HousingCaseAttachment, HousingCitizen, HousingQueueCase
from delayu.services.document_intelligence import apply_uzhv_fields, recognize_upload
from delayu.services.ocr import extract_text_from_upload
from delayu.services.uzhv_ner import extract_application_fields

User = get_user_model()

SAMPLE_TEXT = """
Заявление о признании малоимущими
ФИО: Иванов Иван Иванович
СНИЛС 123-456-789 01
Паспорт 1234 567890
Адрес регистрации: г. Краснодар, ул. Красная, д. 1, кв. 2
Среднемесячный доход: 15 000,50
Состав семьи: 3
Дата заявления: 10.07.2026
Телефон +7 (918) 123-45-67
"""


class OcrNerServiceTests(TestCase):
    def test_extract_application_fields(self):
        fields = extract_application_fields(SAMPLE_TEXT)
        keys = {f["key"] for f in fields}
        self.assertIn("last_name", keys)
        self.assertIn("snils", keys)
        self.assertIn("passport_series", keys)
        self.assertIn("reg_address", keys)
        self.assertIn("monthly_income", keys)
        self.assertIn("household_size", keys)
        self.assertIn("low_income_application_at", keys)

    def test_extract_text_plain(self):
        f = SimpleUploadedFile("t.txt", SAMPLE_TEXT.encode("utf-8"))
        result = extract_text_from_upload(f, filename="t.txt")
        self.assertEqual(result["engine"], "text")
        self.assertIn("Иванов", result["text"])

    def test_recognize_upload_txt(self):
        f = SimpleUploadedFile("app.txt", SAMPLE_TEXT.encode("utf-8"))
        out = recognize_upload(f, filename="app.txt")
        self.assertGreaterEqual(out["field_count"], 5)
        self.assertGreater(out["text_length"], 50)


class OcrUzhvApiTests(TestCase):
    def setUp(self):
        from delayu.models import (
            ModuleCatalog,
            Organization,
            Role,
            RoleModulePermission,
            Subsystem,
            SubsystemMembership,
            SubsystemModule,
        )

        self.sub = Subsystem.objects.create(
            code="ocrsub", name="OCR", industry_template="uzhv", status="active"
        )
        org = Organization.objects.create(subsystem=self.sub, code="o1", name="Org")
        role = Role.objects.create(subsystem=self.sub, code="spec", name="Spec")
        for code in ["M22", "M51"]:
            mod, _ = ModuleCatalog.objects.get_or_create(
                code=code, defaults={"name": code, "group": "core"}
            )
            RoleModulePermission.objects.create(
                role=role, module=mod, can_view=True, can_create=True, can_change=True
            )
            SubsystemModule.objects.create(subsystem=self.sub, module=mod, enabled=True)
        self.user = User.objects.create_user("ocr_user", password="secret")
        SubsystemMembership.objects.create(
            user=self.user, subsystem=self.sub, organization=org, role=role, is_default=True
        )
        profile, _ = UserProfile.objects.get_or_create(user=self.user)
        profile.active_subsystem = self.sub
        profile.save()
        self.citizen = HousingCitizen.objects.create(
            subsystem=self.sub, last_name="Петров", first_name="Пётр"
        )
        self.case = HousingQueueCase.objects.create(
            subsystem=self.sub, citizen=self.citizen, case_number="UZHV-OCR-1"
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_apply_uzhv_fields(self):
        changes = apply_uzhv_fields(
            self.case,
            self.citizen,
            {
                "last_name": "Иванов",
                "first_name": "Иван",
                "snils": "123-456-789 01",
                "household_size": "3",
                "low_income_application_at": "2026-07-10",
            },
            user=self.user,
        )
        self.assertTrue(changes)
        self.citizen.refresh_from_db()
        self.case.refresh_from_db()
        self.assertEqual(self.citizen.last_name, "Иванов")
        self.assertEqual(self.case.household_size, 3)
        self.assertEqual(str(self.case.low_income_application_at), "2026-07-10")

    def test_uzhv_attachment_ocr_preview_api(self):
        att = HousingCaseAttachment.objects.create(
            case=self.case,
            title="Заявление",
            doc_kind=HousingCaseAttachment.DocKind.APPLICATION,
            file=SimpleUploadedFile("z.txt", SAMPLE_TEXT.encode("utf-8")),
            uploaded_by=self.user,
        )
        url = f"/uzhv/cases/{self.case.pk}/attachments/{att.pk}/ocr-preview/"
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["field_count"], 5)

    def test_uzhv_ocr_apply_api(self):
        url = f"/uzhv/cases/{self.case.pk}/ocr-apply/"
        resp = self.client.post(
            url,
            data=json.dumps({"fields": {"last_name": "Сидоров", "first_name": "Сидор"}}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.citizen.refresh_from_db()
        self.assertEqual(self.citizen.last_name, "Сидоров")


class AiModuleDocTests(TestCase):
    def test_build_ai_module_doc_has_functions(self):
        from delayu.services.registry_platform import build_ai_module_doc

        doc = build_ai_module_doc()
        self.assertGreaterEqual(len(doc["functions"]), 7)
        ids = {f["id"] for f in doc["functions"]}
        self.assertIn("ИИ-2", ids)
        self.assertIn("ИИ-7", ids)
