# Generated manually for fuel module

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0056_studio_setup_wave8"),
    ]

    operations = [
        migrations.AddField(
            model_name="subsystem",
            name="public_subdomain",
            field=models.SlugField(
                blank=True,
                help_text="Например novorossiysk → novorossiysk.delau.tech",
                max_length=64,
                verbose_name="Поддомен публичного портала",
            ),
        ),
        migrations.AlterField(
            model_name="subsystem",
            name="industry_template",
            field=models.CharField(
                choices=[
                    ("generic", "Универсальная"),
                    ("municipal", "Муниципалитет"),
                    ("agency", "Ведомство"),
                    ("holding", "Холдинг"),
                    ("uzhv", "АИС УЖВ"),
                    ("fuel", "Топливный пропуск"),
                ],
                default="generic",
                max_length=32,
                verbose_name="Шаблон отрасли",
            ),
        ),
        migrations.CreateModel(
            name="FuelCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(choices=[("I", "Критическая"), ("II", "ЖКХ и транспорт"), ("III", "Экономика"), ("IV", "Предприятия"), ("V", "Население")], max_length=4, verbose_name="Код")),
                ("name", models.CharField(max_length=128, verbose_name="Название")),
                ("daily_limit_liters", models.PositiveSmallIntegerField(default=30, verbose_name="Лимит л/сутки")),
                ("requires_moderation", models.BooleanField(default=True, verbose_name="Требует модерации")),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_categories", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Категория топлива",
                "verbose_name_plural": "Категории топлива",
                "ordering": ["sort_order", "code"],
                "unique_together": {("subsystem", "code")},
            },
        ),
        migrations.CreateModel(
            name="FuelCitizen",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("phone", models.CharField(db_index=True, max_length=32, verbose_name="Телефон")),
                ("full_name", models.CharField(blank=True, max_length=255, verbose_name="ФИО")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="E-mail")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_citizens", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Заявитель (топливо)",
                "verbose_name_plural": "Заявители (топливо)",
                "ordering": ["-created_at"],
                "unique_together": {("subsystem", "phone")},
            },
        ),
        migrations.CreateModel(
            name="FuelAzsStation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, verbose_name="Код")),
                ("name", models.CharField(max_length=255, verbose_name="Название")),
                ("network", models.CharField(blank=True, max_length=128, verbose_name="Сеть")),
                ("address", models.CharField(max_length=512, verbose_name="Адрес")),
                ("latitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="Широта")),
                ("longitude", models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True, verbose_name="Долгота")),
                ("status", models.CharField(choices=[("ok", "Норма"), ("low", "Мало топлива"), ("busy", "Перегрузка"), ("empty", "Нет бензина")], default="ok", max_length=16, verbose_name="Статус")),
                ("stock_liters", models.PositiveIntegerField(default=0, verbose_name="Остаток, л")),
                ("queue_minutes", models.PositiveSmallIntegerField(default=0, verbose_name="Очередь, мин")),
                ("is_accepting_permits", models.BooleanField(default=True, verbose_name="Принимает пропуска")),
                ("fuel_grade", models.CharField(default="АИ-95", max_length=32, verbose_name="Марка")),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_azs_stations", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "АЗС",
                "verbose_name_plural": "АЗС",
                "ordering": ["name"],
                "unique_together": {("subsystem", "code")},
            },
        ),
        migrations.CreateModel(
            name="FuelApplication",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(db_index=True, max_length=32, verbose_name="Номер")),
                ("plate", models.CharField(db_index=True, max_length=16, verbose_name="Госномер")),
                ("vehicle_make", models.CharField(blank=True, max_length=128, verbose_name="Марка ТС")),
                ("inn", models.CharField(blank=True, max_length=12, verbose_name="ИНН")),
                ("org_name", models.CharField(blank=True, max_length=255, verbose_name="Организация")),
                ("status", models.CharField(choices=[("draft", "Черновик"), ("pending", "На проверке"), ("approved", "Одобрено"), ("rejected", "Отклонено")], default="pending", max_length=16, verbose_name="Статус")),
                ("reject_reason", models.TextField(blank=True, verbose_name="Причина отказа")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("assigned_azs", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="assigned_applications", to="delayu.fuelazsstation")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="applications", to="delayu.fuelcategory")),
                ("citizen", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="applications", to="delayu.fuelcitizen")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_applications", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Заявка на пропуск",
                "verbose_name_plural": "Заявки на пропуск",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FuelPermit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=32, unique=True, verbose_name="Номер")),
                ("plate", models.CharField(db_index=True, max_length=16, verbose_name="Госномер")),
                ("max_liters", models.PositiveSmallIntegerField(verbose_name="Лимит, л")),
                ("remaining_liters", models.PositiveSmallIntegerField(verbose_name="Остаток, л")),
                ("valid_until", models.DateTimeField(verbose_name="Действует до")),
                ("manual_code", models.CharField(blank=True, max_length=8, verbose_name="Код для ручного ввода")),
                ("qr_payload", models.TextField(blank=True, verbose_name="Payload QR")),
                ("status", models.CharField(choices=[("active", "Действует"), ("revoked", "Отозван"), ("expired", "Истёк")], default="active", max_length=16, verbose_name="Статус")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("application", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="permit", to="delayu.fuelapplication")),
                ("assigned_azs", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="permits", to="delayu.fuelazsstation")),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="delayu.fuelcategory")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_permits", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Топливный пропуск",
                "verbose_name_plural": "Топливные пропуска",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FuelRedeem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plate", models.CharField(max_length=16, verbose_name="Госномер")),
                ("liters", models.DecimalField(decimal_places=2, max_digits=6, verbose_name="Литры")),
                ("operator_note", models.CharField(blank=True, max_length=255, verbose_name="Примечание")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("azs", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redeems", to="delayu.fuelazsstation")),
                ("permit", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="redeems", to="delayu.fuelpermit")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_redeems", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Отпуск топлива",
                "verbose_name_plural": "Отпуски топлива",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FuelBlacklistEntry",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("plate", models.CharField(blank=True, db_index=True, max_length=16, verbose_name="Госномер")),
                ("inn", models.CharField(blank=True, db_index=True, max_length=12, verbose_name="ИНН")),
                ("reason", models.CharField(max_length=255, verbose_name="Причина")),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fuel_blacklist", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Чёрный список (топливо)",
                "verbose_name_plural": "Чёрный список (топливо)",
            },
        ),
    ]
