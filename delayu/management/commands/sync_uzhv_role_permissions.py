"""Пересчитать RoleModulePermission для ролей АИС УЖВ по матрице uzhv_roles."""
from django.core.management.base import BaseCommand

from delayu.models import ModuleCatalog, Role, RoleModulePermission, Subsystem
from delayu.services.uzhv_roles import perm_for_role


class Command(BaseCommand):
    help = "Обновить права ролей подсистемы УЖВ (после изменения uzhv_roles.py)"

    def handle(self, *args, **options):
        subsystem = Subsystem.objects.filter(code="uzhv").first()
        if not subsystem:
            self.stderr.write("Подсистема uzhv не найдена. Сначала: python manage.py seed_uzhv")
            return
        roles = Role.objects.filter(subsystem=subsystem)
        modules = list(ModuleCatalog.objects.all())
        count = 0
        for role in roles:
            for mod in modules:
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults=perm_for_role(role.code, mod.code),
                )
                count += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Обновлено {count} записей прав для {roles.count()} ролей (подсистема {subsystem.code})"
            )
        )
