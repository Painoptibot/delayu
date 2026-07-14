"""Демо-данные для экспертизы реестра (DEMO-P0-01)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from delayu.models import KnowledgeArticle, Subsystem
from delayu.models_uzhv import HousingCaseAttachment, HousingCitizen, HousingQueueCase
from delayu.services.uzhv_low_income import compute_low_income_review_due

User = get_user_model()

DEMO_APPLICATION_TEXT = """
Заявление о признании малоимущими (демо реестра)
ФИО: Демов Эксперт Тестович
СНИЛС 111-222-333 44
Паспорт 4010 123456
Адрес регистрации: г. Краснодар, ул. Красная, д. 10, кв. 5
Среднемесячный доход: 18 500,00
Состав семьи: 2
Дата заявления: 01.07.2026
Телефон +7 (918) 555-00-11
""".strip()


class Command(BaseCommand):
    help = "Seed для сценария экспертизы реестра: OCR, полнота, поиск (DEMO-P0-01)"

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command("seed_uzhv", verbosity=0)
        call_command("seed_registry_platform", verbosity=0)

        subsystem = Subsystem.objects.get(code="uzhv")
        spec = User.objects.filter(username="uzhv_spec").first()
        if not spec:
            self.stderr.write("Пользователь uzhv_spec не найден после seed_uzhv")
            return

        citizen, _ = HousingCitizen.objects.update_or_create(
            subsystem=subsystem,
            snils="111-222-333 44",
            defaults={
                "last_name": "Демов",
                "first_name": "Эксперт",
                "middle_name": "Тестович",
                "reg_address": "г. Краснодар, ул. Красная, д. 10, кв. 5",
                "phone": "+79185550011",
            },
        )

        app_date = timezone.now().date() - timedelta(days=5)
        case, created = HousingQueueCase.objects.update_or_create(
            subsystem=subsystem,
            case_number="УЖВ-DEMO-REG",
            defaults={
                "citizen": citizen,
                "category": HousingQueueCase.Category.LOW_INCOME,
                "status": HousingQueueCase.Status.REGISTERED,
                "assignee": spec,
                "household_size": 2,
                "low_income_application_at": app_date,
                "low_income_review_due_at": compute_low_income_review_due(app_date, subsystem),
                "low_income_eligible": None,
                "income_verified": False,
                "notes": "Демо-дело для экспертизы реестра (OCR + полнота пакета).",
            },
        )

        case.attachments.all().delete()
        HousingCaseAttachment.objects.create(
            case=case,
            title="Заявление о признании малоимущими",
            doc_kind=HousingCaseAttachment.DocKind.APPLICATION,
            file=SimpleUploadedFile(
                "zayavlenie_demo.txt",
                DEMO_APPLICATION_TEXT.encode("utf-8"),
                content_type="text/plain",
            ),
            uploaded_by=spec,
        )
        HousingCaseAttachment.objects.create(
            case=case,
            title="Паспорт заявителя (скан)",
            doc_kind=HousingCaseAttachment.DocKind.PASSPORT,
            file=SimpleUploadedFile(
                "passport_demo.txt",
                "Паспорт РФ серия 4010 номер 123456 выдан УФМС г. Краснодар".encode("utf-8"),
                content_type="text/plain",
            ),
            uploaded_by=spec,
        )

        KnowledgeArticle.objects.update_or_create(
            subsystem=subsystem,
            title="Признание малоимущими — порядок рассмотрения",
            defaults={
                "body": (
                    "Заявление о признании семьи малоимущей рассматривается в срок до 30 дней. "
                    "Необходимы: заявление, паспорт, справки о доходах всех членов семьи, "
                    "сведения об имуществе. Решение оформляется заключением и вносится в учётное дело."
                ),
                "tags": "малоимущие, заявление, ужв, реестр",
                "is_published": True,
            },
        )

        from delayu.services.uzhv import register_housing_appeal

        register_housing_appeal(
            subsystem=subsystem,
            user=spec,
            subject="Жалоба на срок рассмотрения заявления малоимущих (демо реестра)",
            body="Заявление подано более месяца назад, прошу сообщить статус.",
            citizen=citizen,
            housing_case=case,
            assignee=spec,
            received_at=timezone.now().date() - timedelta(days=28),
        )

        from delayu.services.document_completeness import housing_case_completeness

        pack = housing_case_completeness(case)
        action = "создано" if created else "обновлено"
        self.stdout.write(
            self.style.SUCCESS(
                f"Демо-дело {case.case_number} ({action}, id={case.pk}). "
                f"Полнота: {pack['summary']}"
            )
        )
        self.stdout.write("Вход: uzhv_spec / uzhv_spec")
        self.stdout.write(f"Сценарий OCR: /uzhv/cases/{case.pk}/low-income/")
        self.stdout.write("Инструкция: /exploit/demo-guide/")
        self.stdout.write("Заявление: /exploit/registry-application/")
