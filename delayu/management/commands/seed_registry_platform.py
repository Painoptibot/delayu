"""Заполнение паспорта продукта, глоссария и журнала соответствия реестру."""
from django.core.management.base import BaseCommand

from delayu.services.registry_platform import seed_registry_catalog


class Command(BaseCommand):
    help = "Релиз, глоссарий и журнал соответствия модулей для реестра Минцифры"

    def handle(self, *args, **options):
        result = seed_registry_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                f"Релиз v{result['release']}, глоссарий +{result['glossary_new']}, "
                f"соответствие модулей: {result['compliance']}"
            )
        )
