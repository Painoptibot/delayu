import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0107_service_office"),
    ]

    operations = [
        migrations.CreateModel(
            name="ServiceField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder", models.CharField(blank=True, max_length=128, verbose_name="Папка")),
                ("name", models.CharField(max_length=255, verbose_name="Поле")),
                ("field_type", models.CharField(max_length=64, verbose_name="Тип")),
                ("record", models.CharField(choices=[("contact", "Контакт"), ("opportunity", "Сделка"), ("company", "Компания")], default="contact", max_length=16, verbose_name="Карточка")),
                ("key", models.CharField(max_length=180, verbose_name="Ключ")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_fields", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Своё поле",
                "verbose_name_plural": "Свои поля",
                "ordering": ["folder", "name"],
                "unique_together": {("subsystem", "key")},
            },
        ),
        migrations.CreateModel(
            name="ServiceForm",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder", models.CharField(blank=True, max_length=128, verbose_name="Папка")),
                ("name", models.CharField(max_length=255, verbose_name="Форма")),
                ("prompt", models.TextField(blank=True, verbose_name="Что спрашивает")),
                ("status", models.CharField(choices=[("active", "Активна"), ("draft", "Черновик")], default="active", max_length=16, verbose_name="Статус")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_forms", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Форма",
                "verbose_name_plural": "Формы",
                "ordering": ["folder", "name"],
                "unique_together": {("subsystem", "name")},
            },
        ),
        migrations.CreateModel(
            name="ServicePhone",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=32, verbose_name="Номер")),
                ("title", models.CharField(max_length=128, verbose_name="Имя")),
                ("forward_to", models.CharField(blank=True, max_length=32, verbose_name="Переадресация")),
                ("timeout_seconds", models.PositiveIntegerField(default=60, verbose_name="Таймаут, с")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_phones", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Номер",
                "verbose_name_plural": "Номера",
                "ordering": ["title"],
                "unique_together": {("subsystem", "number")},
            },
        ),
        migrations.CreateModel(
            name="ServiceStaff",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Имя")),
                ("email", models.EmailField(max_length=254, verbose_name="Почта")),
                ("role_name", models.CharField(max_length=64, verbose_name="Роль")),
                ("subsystem", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_staff", to="delayu.subsystem")),
            ],
            options={
                "verbose_name": "Сотрудник локации",
                "verbose_name_plural": "Сотрудники локации",
                "ordering": ["name"],
                "unique_together": {("subsystem", "email")},
            },
        ),
    ]
