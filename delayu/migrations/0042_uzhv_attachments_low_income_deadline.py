# УЖВ: срок рассмотрения малоимущих, вложения к делам

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("delayu", "0041_uzhv_household_passport_contracts"),
    ]

    operations = [
        migrations.AddField(
            model_name="housingqueuecase",
            name="low_income_application_at",
            field=models.DateField(
                blank=True, null=True, verbose_name="Дата заявления (малоимущие)"
            ),
        ),
        migrations.AddField(
            model_name="housingqueuecase",
            name="low_income_review_due_at",
            field=models.DateField(
                blank=True, null=True, verbose_name="Срок рассмотрения заявления"
            ),
        ),
        migrations.CreateModel(
            name="HousingCaseAttachment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("title", models.CharField(max_length=255, verbose_name="Наименование")),
                (
                    "doc_kind",
                    models.CharField(
                        choices=[
                            ("application", "Заявление"),
                            ("passport", "Паспорт / удостоверение"),
                            ("income", "Справка о доходах"),
                            ("property", "Сведения об имуществе"),
                            ("decision", "Решение / заключение"),
                            ("other", "Прочее"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("file", models.FileField(upload_to="uzhv/cases/%Y/%m/", verbose_name="Файл")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="delayu.housingqueuecase",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="uzhv_attachments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Вложение к делу УЖВ",
                "verbose_name_plural": "Вложения к делам УЖВ",
                "ordering": ["-uploaded_at"],
            },
        ),
    ]
