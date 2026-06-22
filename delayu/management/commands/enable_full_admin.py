"""Полный доступ главного администратора: выключить демо и выдать все права."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.models import (
    ModuleCatalog,
    PiiMaskingPolicy,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemModule,
)
from delayu.menu import ensure_superuser_membership

User = get_user_model()


class Command(BaseCommand):
    help = "Отключить демо-режим и выдать полные права администратору платформы"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="admin",
            help="Логин главного администратора (по умолчанию: admin)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        user = User.objects.filter(username=username).first()
        if not user:
            self.stderr.write(self.style.ERROR(f"Пользователь {username} не найден"))
            return

        user.is_superuser = True
        user.is_staff = True
        user.is_active = True
        user.save(update_fields=["is_superuser", "is_staff", "is_active"])

        disabled = PiiMaskingPolicy.objects.filter(demo_mode=True).update(demo_mode=False)
        self.stdout.write(f"Демо-режим выключен на {disabled} подсистемах")

        membership = ensure_superuser_membership(user)
        if not membership:
            self.stderr.write(self.style.WARNING("Нет подсистемы для membership"))
            return

        subsystems = Subsystem.objects.exclude(status=Subsystem.Status.ARCHIVED)
        granted = 0
        for sub in subsystems:
            admin_role = (
                Role.objects.filter(subsystem=sub, code="admin").first()
                or Role.objects.filter(subsystem=sub, code="uzhv_admin").first()
                or Role.objects.filter(subsystem=sub, is_system=True).first()
            )
            if not admin_role:
                continue
            for mod in ModuleCatalog.objects.all():
                SubsystemModule.objects.update_or_create(
                    subsystem=sub,
                    module=mod,
                    defaults={"enabled": True},
                )
                _, created = RoleModulePermission.objects.update_or_create(
                    role=admin_role,
                    module=mod,
                    defaults={
                        "can_view": True,
                        "can_create": True,
                        "can_change": True,
                        "can_delete": True,
                        "can_view_pii": True,
                        "can_export_pii": True,
                        "can_approve": True,
                        "can_sign": True,
                        "can_archive": True,
                        "can_bulk": True,
                    },
                )
                if created:
                    granted += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"{username}: superuser, демо выкл., membership в «{membership.subsystem.code}», "
                f"обновлены права роли администратора (+{granted} новых записей)"
            )
        )
