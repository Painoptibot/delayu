import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def add_service_modules(apps, schema_editor):
    ModuleCatalog = apps.get_model("delayu", "ModuleCatalog")
    ModuleCatalog.objects.update_or_create(
        code="S01",
        defaults={
            "name": "Карточка заказчика",
            "group": "comms",
            "is_core": False,
            "sort_order": 131,
            "is_active": True,
        },
    )
    ModuleCatalog.objects.update_or_create(
        code="S02",
        defaults={
            "name": "Объекты и выезды",
            "group": "cases",
            "is_core": False,
            "sort_order": 132,
            "is_active": True,
        },
    )


def remove_service_modules(apps, schema_editor):
    ModuleCatalog = apps.get_model("delayu", "ModuleCatalog")
    ModuleCatalog.objects.filter(code__in=["S01", "S02"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0102_merge_stand_license"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
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
                    ("invest", "Инвестконтур"),
                    ("service", "Сервисный контур"),
                ],
                default="generic",
                max_length=32,
                verbose_name="Шаблон отрасли",
            ),
        ),
        migrations.CreateModel(
            name="ServiceCustomer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(db_index=True, max_length=32, verbose_name="Номер")),
                ("display_name", models.CharField(max_length=255, verbose_name="Заказчик")),
                ("company", models.CharField(blank=True, max_length=255, verbose_name="Организация")),
                ("phone", models.CharField(blank=True, max_length=32, verbose_name="Телефон")),
                ("email", models.EmailField(blank=True, max_length=254, verbose_name="Почта")),
                ("address", models.CharField(blank=True, max_length=512, verbose_name="Адрес")),
                ("stage", models.CharField(choices=[("lead", "Заявка"), ("survey", "Обследование"), ("work", "Работы"), ("acceptance", "Приёмка"), ("done", "Завершено")], default="lead", max_length=16, verbose_name="Этап")),
                ("payment_state", models.CharField(choices=[("none", "Нет счёта"), ("invoiced", "Счёт выставлен"), ("partial", "Частично оплачено"), ("paid", "Оплачено")], default="none", max_length=16, verbose_name="Оплата")),
                ("invoice_amount", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name="Сумма счёта")),
                ("tags", models.CharField(blank=True, max_length=255, verbose_name="Метки")),
                ("notes", models.TextField(blank=True, verbose_name="Заметки")),
                ("attributes", models.JSONField(blank=True, default=dict, verbose_name="Дополнительные атрибуты")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_customers", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Заказчик сервисного контура",
                "verbose_name_plural": "Заказчики сервисного контура",
                "ordering": ["-updated_at"],
                "unique_together": {("subsystem", "number")},
            },
        ),
        migrations.CreateModel(
            name="ServiceChannel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, verbose_name="Код")),
                ("title", models.CharField(max_length=64, verbose_name="Канал")),
                ("detail", models.CharField(max_length=255, verbose_name="Как попадает в карточку")),
                ("status", models.CharField(choices=[("ready", "Принимает в карточку"), ("paused", "На паузе")], default="ready", max_length=16, verbose_name="Статус")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_channels", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Канал диалога",
                "verbose_name_plural": "Каналы диалога",
                "ordering": ["title"],
                "unique_together": {("subsystem", "code")},
            },
        ),
        migrations.CreateModel(
            name="ServiceObject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, verbose_name="Код")),
                ("title", models.CharField(max_length=255, verbose_name="Объект")),
                ("address", models.CharField(blank=True, max_length=512, verbose_name="Адрес")),
                ("stage", models.CharField(choices=[("lead", "Заявка"), ("survey", "Обследование"), ("work", "Работы"), ("acceptance", "Приёмка"), ("done", "Завершено")], default="survey", max_length=16, verbose_name="Этап работ")),
                ("status", models.CharField(choices=[("planned", "Запланирован"), ("active", "В работе"), ("paused", "Пауза"), ("done", "Завершён")], default="planned", max_length=16, verbose_name="Статус")),
                ("notes", models.TextField(blank=True, verbose_name="Заметки")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="sites", to="delayu.servicecustomer")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_objects", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Объект",
                "verbose_name_plural": "Объекты",
                "ordering": ["title"],
                "unique_together": {("subsystem", "code")},
            },
        ),
        migrations.CreateModel(
            name="ServiceMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(max_length=32, verbose_name="Канал")),
                ("direction", models.CharField(choices=[("in", "Входящее"), ("out", "Исходящее")], max_length=8, verbose_name="Направление")),
                ("author_kind", models.CharField(choices=[("customer", "Заказчик"), ("staff", "Сотрудник"), ("agent", "ИИ-агент")], max_length=16, verbose_name="Автор")),
                ("kind", models.CharField(choices=[("dialogue", "Диалог"), ("answer", "Ответ агента"), ("stage", "Этап работ"), ("payment", "Оплата")], default="dialogue", max_length=16, verbose_name="Вид")),
                ("body", models.TextField(verbose_name="Текст")),
                ("status", models.CharField(choices=[("scheduled", "Ждёт срока"), ("sent", "В карточке")], default="sent", max_length=16, verbose_name="Статус")),
                ("scheduled_for", models.DateTimeField(blank=True, null=True, verbose_name="Срок отправки")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="Попало в карточку")),
                ("last_error", models.CharField(blank=True, max_length=255, verbose_name="Почему не ушло")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="service_messages", to=settings.AUTH_USER_MODEL)),
                ("customer", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="delayu.servicecustomer")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_messages", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Сообщение карточки",
                "verbose_name_plural": "Сообщения карточки",
                "ordering": ["created_at", "pk"],
            },
        ),
        migrations.CreateModel(
            name="ServiceVisit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("departed_on", models.DateField(verbose_name="Дата выезда")),
                ("distance_km", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Километры")),
                ("rate_per_km", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Ставка за км")),
                ("hours", models.DecimalField(decimal_places=2, default=0, max_digits=8, verbose_name="Часы на объекте")),
                ("hour_rate", models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name="Ставка часа")),
                ("other_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Прочие издержки")),
                ("travel_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Дорога")),
                ("labor_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Работа")),
                ("total_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Итого выезд")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                ("employee", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_visits", to=settings.AUTH_USER_MODEL)),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="visits", to="delayu.serviceobject")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_visits", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Выезд",
                "verbose_name_plural": "Выезды",
                "ordering": ["-departed_on", "-pk"],
            },
        ),
        migrations.CreateModel(
            name="ServiceDeployment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("people", "Люди"), ("vehicle", "Транспорт"), ("equipment", "Техника"), ("material", "Материалы")], max_length=16, verbose_name="Вид")),
                ("title", models.CharField(max_length=255, verbose_name="Наименование")),
                ("quantity", models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Количество")),
                ("unit", models.CharField(default="шт", max_length=32, verbose_name="Единица")),
                ("unit_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Цена единицы")),
                ("total_cost", models.DecimalField(decimal_places=2, default=0, max_digits=12, verbose_name="Сумма")),
                ("note", models.CharField(blank=True, max_length=255, verbose_name="Комментарий")),
                ("site", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="deployments", to="delayu.serviceobject")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_deployments", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Силы и средства",
                "verbose_name_plural": "Силы и средства",
                "ordering": ["kind", "title"],
            },
        ),
        migrations.RunPython(add_service_modules, remove_service_modules),
    ]
