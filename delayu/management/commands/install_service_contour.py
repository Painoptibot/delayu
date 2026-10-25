"""Постановка сервисного контура: модули платформы и разделы карточки."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.data.modules_full import MODULES_FULL
from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.services.service_channels import ensure_channels

User = get_user_model()


class Command(BaseCommand):
    help = "Создаёт сервисный контур и включает каталог модулей плюс карточку заказчика."

    def add_arguments(self, parser):
        parser.add_argument("--code", default="service")
        parser.add_argument("--name", default="Сервисный контур")

    def handle(self, *args, **options):
        code = options["code"]
        name = options["name"]
        for row in MODULES_FULL:
            ModuleCatalog.objects.update_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "group": row["group"],
                    "is_core": row.get("is_core", False),
                    "sort_order": row.get("sort_order", 0),
                    "is_active": True,
                },
            )
        subsystem = Subsystem.objects.filter(code=code).first()
        if subsystem and subsystem.industry_template != "service":
            self.stderr.write(
                f"Контур {code} уже есть как «{subsystem.industry_template}». Код не перезаписан."
            )
            return
        if subsystem is None:
            subsystem = Subsystem.objects.create(
                code=code,
                name=name,
                status=Subsystem.Status.ACTIVE,
                industry_template="service",
                description="Карточка заказчика, каналы диалога и учёт объектов.",
            )
        else:
            subsystem.name = name
            subsystem.status = Subsystem.Status.ACTIVE
            subsystem.industry_template = "service"
            subsystem.save(update_fields=["name", "status", "industry_template"])
        org, _created = Organization.objects.get_or_create(
            subsystem=subsystem, code="main", defaults={"name": name}
        )
        role, _created = Role.objects.get_or_create(
            subsystem=subsystem,
            code="service_admin",
            defaults={"name": "Администратор сервиса", "is_subsystem_admin": True},
        )
        for module in ModuleCatalog.objects.all():
            SubsystemModule.objects.get_or_create(
                subsystem=subsystem, module=module, defaults={"enabled": True}
            )
            RoleModulePermission.objects.update_or_create(
                role=role,
                module=module,
                defaults={"can_view": True, "can_create": True, "can_change": True},
            )
        ensure_channels(subsystem)
        from delayu.services.service_process import ensure_process
        from delayu.services.service_snapshot import load_canadian_led

        ensure_process(subsystem)
        load_canadian_led(subsystem)
        attached = 0
        for user in User.objects.filter(is_superuser=True):
            membership, created = SubsystemMembership.objects.get_or_create(
                user=user,
                subsystem=subsystem,
                organization=org,
                role=role,
                defaults={"is_default": not user.subsystem_memberships.exists()},
            )
            if created:
                attached += 1
        office = self._office_logins(subsystem, org, role)
        self.stdout.write(
            self.style.SUCCESS(
                f"Сервисный контур {subsystem.code}: модулей {subsystem.module_links.count()}, "
                f"суперпользователей добавлено {attached}, входы офиса {office}."
            )
        )

    def _office_logins(self, subsystem, org, role):
        people = (
            ("vladimir", "237779@list.ru", "Владимир", "Ху"),
            ("vitaly", "info@canadian-led.com", "Виталий", "Кочанов"),
        )
        opened = 0
        for username, email, first, last in people:
            user = User.objects.filter(username=username).first()
            if user is None:
                user = User(
                    username=username,
                    email=email,
                    first_name=first,
                    last_name=last,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save()
                opened += 1
            else:
                user.email = email
                user.first_name = first
                user.last_name = last
                user.is_active = True
                user.save(update_fields=["email", "first_name", "last_name", "is_active"])
            SubsystemMembership.objects.get_or_create(
                user=user,
                subsystem=subsystem,
                organization=org,
                role=role,
                defaults={"is_default": not user.subsystem_memberships.exists()},
            )
        return opened
