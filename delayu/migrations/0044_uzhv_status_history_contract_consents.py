# ТЗ п. 277 — история статусов; п. 297–305 — согласия и вложения по договорам

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0043_uzhv_tz_premises_removal_forms"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HousingCaseStatusHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "from_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("draft", "Черновик"),
                            ("registered", "На учёте"),
                            ("queued", "В очереди"),
                            ("provided", "Обеспечен"),
                            ("removed", "Снят с учёта"),
                            ("rejected", "Отказ"),
                        ],
                        max_length=20,
                        verbose_name="Было",
                    ),
                ),
                (
                    "to_status",
                    models.CharField(
                        choices=[
                            ("draft", "Черновик"),
                            ("registered", "На учёте"),
                            ("queued", "В очереди"),
                            ("provided", "Обеспечен"),
                            ("removed", "Снят с учёта"),
                            ("rejected", "Отказ"),
                        ],
                        max_length=20,
                        verbose_name="Стало",
                    ),
                ),
                ("changed_at", models.DateTimeField(auto_now_add=True)),
                ("comment", models.TextField(blank=True, verbose_name="Комментарий / основание")),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="status_history",
                        to="delayu.housingqueuecase",
                    ),
                ),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="uzhv_case_status_changes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "История статуса дела",
                "verbose_name_plural": "История статусов дел",
                "ordering": ["-changed_at"],
            },
        ),
        migrations.CreateModel(
            name="HousingContractConsent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "consent_type",
                    models.CharField(
                        choices=[
                            ("sublet", "Поднайм"),
                            ("move_in", "Вселение членов семьи"),
                            ("exchange", "Обмен жилого помещения"),
                            ("temp_ban", "Запрет временных жильцов"),
                            ("termination_ob", "Обязательство о расторжении"),
                            ("emergency", "Соглашение об изъятии (аварийный)"),
                            ("privatization", "Передача в собственность"),
                            ("private_to_muni", "Безвозмездная передача в муниципальную"),
                        ],
                        max_length=20,
                        verbose_name="Вид",
                    ),
                ),
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("pending", "На оформлении"),
                            ("approved", "Согласие"),
                            ("denied", "Отказ"),
                            ("registered", "Зарегистрировано"),
                        ],
                        default="pending",
                        max_length=16,
                        verbose_name="Решение",
                    ),
                ),
                (
                    "subject",
                    models.CharField(
                        blank=True,
                        max_length=500,
                        verbose_name="Содержание (кого вселяют, с кем обмен и т.п.)",
                    ),
                ),
                ("document_number", models.CharField(blank=True, max_length=64, verbose_name="№ документа")),
                (
                    "registered_at",
                    models.DateField(default=django.utils.timezone.now, verbose_name="Дата регистрации"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Примечание")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="consents",
                        to="delayu.housingcontract",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="uzhv_contract_consents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Согласие / действие по договору",
                "verbose_name_plural": "Согласия и действия по договорам",
                "ordering": ["-registered_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="HousingContractAttachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255, verbose_name="Наименование")),
                (
                    "doc_kind",
                    models.CharField(
                        choices=[
                            ("contract", "Договор"),
                            ("consent", "Согласие / отказ"),
                            ("agreement", "Соглашение"),
                            ("other", "Прочее"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("file", models.FileField(upload_to="uzhv/contracts/%Y/%m/", verbose_name="Файл")),
                ("uploaded_at", models.DateTimeField(auto_now_add=True)),
                (
                    "contract",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="delayu.housingcontract",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="uzhv_contract_files",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Вложение к договору",
                "verbose_name_plural": "Вложения к договорам",
                "ordering": ["-uploaded_at"],
            },
        ),
    ]
