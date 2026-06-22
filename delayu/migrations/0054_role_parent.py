from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0053_backfill_action_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="parent_role",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="child_roles",
                to="delayu.role",
                verbose_name="Наследует права от",
            ),
        ),
    ]
