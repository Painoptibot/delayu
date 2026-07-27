from django.db import migrations, models


def seed_smev_info_types(apps, schema_editor):
    InvestSmevInfoType = apps.get_model("delayu", "InvestSmevInfoType")
    defaults = [
        (
            "egrn-basic",
            {
                "name": "ЕГРН: сведения об участке",
                "service": "egrn",
                "contract_version": "demo-1",
                "schema_json": {
                    "required": ["cadastral_number", "address", "area_ha", "land_category"],
                },
                "is_active": True,
            },
        ),
        (
            "isogd-zone",
            {
                "name": "ИСОГД: градостроительные зоны",
                "service": "isogd",
                "contract_version": "demo-1",
                "schema_json": {"required": ["note"]},
                "is_active": True,
            },
        ),
        (
            "rgis-intersections",
            {
                "name": "РГИС: пересечения и ограничения",
                "service": "rgis",
                "contract_version": "demo-1",
                "schema_json": {"required": ["note"]},
                "is_active": True,
            },
        ),
    ]
    for code, values in defaults:
        InvestSmevInfoType.objects.update_or_create(code=code, defaults=values)


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0084_invest_levelup_p6"),
    ]

    operations = [
        migrations.AddField(
            model_name="investsmevrequest",
            name="audit_trail",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="correlation_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="dead_lettered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="max_retries",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="message_id",
            field=models.CharField(blank=True, db_index=True, max_length=64),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="retries",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="investsmevrequest",
            name="timeout_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="investsmevrequest",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "В очереди"),
                    ("live_pending", "Ожидает live-ответ"),
                    ("done", "Получен ответ"),
                    ("error", "Ошибка"),
                    ("applied", "Применено к карточке"),
                    ("dead_letter", "Dead-letter"),
                    ("timeout", "Таймаут"),
                    ("schema_error", "Ошибка схемы"),
                ],
                default="queued",
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="InvestSmevInfoType",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=255)),
                (
                    "service",
                    models.CharField(
                        choices=[
                            ("egrn", "ЕГРН (кадастр / права)"),
                            ("isogd", "ИСОГД / ФГИС ТП"),
                            ("rgis", "РГИС (пересечения)"),
                        ],
                        max_length=16,
                    ),
                ),
                ("contract_version", models.CharField(blank=True, max_length=64)),
                ("schema_json", models.JSONField(blank=True, default=dict)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Вид сведений СМЭВ",
                "verbose_name_plural": "Виды сведений СМЭВ",
                "ordering": ["service", "code"],
            },
        ),
        migrations.RunPython(seed_smev_info_types, migrations.RunPython.noop),
    ]
