"""Два демо-провайдера ЕСИА для страницы входа."""

from django.core.management.base import BaseCommand

from delayu.management.commands.seed_uzhv import Command as SeedUzhvCommand
from delayu.models import Subsystem


class Command(BaseCommand):
    help = "Создать/обновить 2 кнопки «ЕСИА (демо)» на странице входа"

    def handle(self, *args, **options):
        seed = SeedUzhvCommand()
        count = 0
        for subsystem in Subsystem.objects.filter(industry_template="uzhv"):
            seed._seed_sso_demo(subsystem)
            count += 1
        if count:
            self.stdout.write(self.style.SUCCESS(f"ЕСИА (демо) обновлены для {count} подсистем(ы)"))
        else:
            self.stdout.write("Подсистема uzhv не найдена — сначала: python manage.py seed_uzhv")
