"""Скопировать can_change в новые флаги действий для существующих ролей."""

from django.db import migrations


def backfill_action_permissions(apps, schema_editor):
    RoleModulePermission = apps.get_model("delayu", "RoleModulePermission")
    RoleModulePermission.objects.filter(can_change=True).update(
        can_approve=True,
        can_sign=True,
        can_archive=True,
        can_bulk=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("delayu", "0052_studio_wave2"),
    ]

    operations = [
        migrations.RunPython(backfill_action_permissions, migrations.RunPython.noop),
    ]
