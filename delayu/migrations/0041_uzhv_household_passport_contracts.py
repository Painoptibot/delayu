# УЖВ: паспорт, состав семьи, поля договора

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0040_s4_wave"),
    ]

    operations = [
        migrations.AddField(
            model_name="housingcitizen",
            name="passport_issued_at",
            field=models.DateField(blank=True, null=True, verbose_name="Дата выдачи паспорта"),
        ),
        migrations.AddField(
            model_name="housingcitizen",
            name="passport_issued_by",
            field=models.CharField(blank=True, max_length=255, verbose_name="Кем выдан"),
        ),
        migrations.AddField(
            model_name="housingcitizen",
            name="passport_number",
            field=models.CharField(blank=True, max_length=12, verbose_name="Номер паспорта"),
        ),
        migrations.AddField(
            model_name="housingcitizen",
            name="passport_series",
            field=models.CharField(blank=True, max_length=8, verbose_name="Серия паспорта"),
        ),
        migrations.AddField(
            model_name="housingcontract",
            name="notes",
            field=models.TextField(blank=True, verbose_name="Примечание"),
        ),
        migrations.AddField(
            model_name="housingcontract",
            name="terminated_at",
            field=models.DateField(blank=True, null=True, verbose_name="Дата расторжения"),
        ),
        migrations.AddField(
            model_name="housingcontract",
            name="termination_reason",
            field=models.CharField(blank=True, max_length=500, verbose_name="Основание расторжения"),
        ),
        migrations.CreateModel(
            name="HousingHouseholdMember",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("full_name", models.CharField(max_length=255, verbose_name="ФИО")),
                (
                    "relation",
                    models.CharField(
                        choices=[
                            ("applicant", "Заявитель"),
                            ("spouse", "Супруг(а)"),
                            ("child", "Ребёнок"),
                            ("dependent", "Иждивенец"),
                            ("other", "Иное"),
                        ],
                        default="other",
                        max_length=16,
                    ),
                ),
                ("birth_date", models.DateField(blank=True, null=True, verbose_name="Дата рождения")),
                (
                    "monthly_income",
                    models.DecimalField(
                        blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Месячный доход, ₽"
                    ),
                ),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="household_members",
                        to="delayu.housingqueuecase",
                    ),
                ),
            ],
            options={
                "verbose_name": "Член семьи",
                "verbose_name_plural": "Состав семьи",
                "ordering": ["sort_order", "pk"],
            },
        ),
    ]
