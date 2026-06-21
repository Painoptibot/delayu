"""Загрузка полного каталога M01–M86 из ТЗ (без демо-пользователей)."""
from django.core.management.base import BaseCommand

from delayu.data.modules_full import MODULES_FULL
from delayu.models import ModuleCatalog


class Command(BaseCommand):
    help = "Загрузить полный каталог модулей M01–M86"

    def handle(self, *args, **options):
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
        self.stdout.write(self.style.SUCCESS(f"Каталог: {len(MODULES_FULL)} модулей"))
