"""Привязать superuser к подсистеме УЖВ (полное меню и сводка)."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.menu import ensure_superuser_membership

User = get_user_model()


class Command(BaseCommand):
    help = "Создать membership admin в УЖВ для всех superuser без контура"

    def handle(self, *args, **options):
        for user in User.objects.filter(is_superuser=True, is_active=True):
            m = ensure_superuser_membership(user)
            if m:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{user.username} → {m.subsystem.code} / {m.role.code}"
                    )
                )
            else:
                self.stderr.write(
                    self.style.WARNING(
                        f"{user.username}: нет подсистемы — выполните seed_uzhv"
                    )
                )
