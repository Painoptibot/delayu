# ТЗ: непригодные помещения, снятие с учёта, молодые семьи, сироты

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0042_uzhv_attachments_low_income_deadline"),
    ]

    operations = [
        migrations.AddField(
            model_name="housingqueuecase",
            name="removed_at",
            field=models.DateField(blank=True, null=True, verbose_name="Дата снятия с учёта"),
        ),
        migrations.AddField(
            model_name="housingqueuecase",
            name="removal_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("provided", "Предоставлено жилое помещение"),
                    ("lost_eligibility", "Утрата оснований"),
                    ("refused", "Отказ заявителя"),
                    ("duplicate", "Дублирование учёта"),
                    ("other", "Иное"),
                ],
                max_length=32,
                verbose_name="Основание снятия с учёта",
            ),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="specialized_orphan",
            field=models.BooleanField(
                default=False, verbose_name="Специализированное (дети-сироты)"
            ),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="unfit_decision_at",
            field=models.DateField(blank=True, null=True, verbose_name="Дата признания непригодным"),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="unfit_decision_ref",
            field=models.CharField(
                blank=True, max_length=128, verbose_name="№ акта / решения о непригодности"
            ),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="unfit_for_living",
            field=models.BooleanField(
                default=False, verbose_name="Непригодно для проживания"
            ),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="unfit_reason",
            field=models.TextField(blank=True, verbose_name="Основание непригодности"),
        ),
        migrations.AddField(
            model_name="municipalpremise",
            name="usable_for_purpose",
            field=models.BooleanField(
                default=True, verbose_name="Пригодно к использованию по назначению"
            ),
        ),
        migrations.AddField(
            model_name="orphanhousingrecord",
            name="assigned_premise",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="orphan_assignments",
                to="delayu.municipalpremise",
                verbose_name="Закреплённое спец. помещение",
            ),
        ),
        migrations.AddField(
            model_name="youngfamilyrecord",
            name="criteria_checked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="youngfamilyrecord",
            name="criteria_notes",
            field=models.TextField(blank=True, verbose_name="Заключение по критериям"),
        ),
        migrations.AddField(
            model_name="youngfamilyrecord",
            name="spouse_birth_date",
            field=models.DateField(blank=True, null=True, verbose_name="Дата рождения супруга(и)"),
        ),
    ]
