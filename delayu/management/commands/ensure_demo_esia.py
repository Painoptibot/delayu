"""Два демо-провайдера ЕСИА для страницы входа."""

from django.core.management.base import BaseCommand

from delayu.management.commands.seed_uzhv import Command as SeedUzhvCommand
from delayu.models import Subsystem


class Command(BaseCommand):
    help = "Создать/обновить одну кнопку «ЕСИА (демо)» на странице входа"

    def handle(self, *args, **options):
        seed = SeedUzhvCommand()
        count = 0
        for subsystem in Subsystem.objects.filter(industry_template="uzhv"):
            seed._seed_sso_demo(subsystem)
            count += 1
        if count:
            self.stdout.write(self.style.SUCCESS(f"ЕСИА (демо) обновлена для {count} подсистем(ы)"))
        else:
            self.stdout.write("Подсистема uzhv не найдена — сначала: python manage.py seed_uzhv")
        from delayu.models import SsoProvider

        disabled = SsoProvider.objects.filter(client_id="demo-esia-org", is_active=True).update(is_active=False)
        if disabled:
            self.stdout.write(f"Отключено дублей ЕСИА (org): {disabled}")
