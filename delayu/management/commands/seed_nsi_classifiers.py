from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.nsi_choices import sync_classifiers_for_subsystem


class Command(BaseCommand):
    help = "Синхронизировать справочники НСИ из каталога форм (выпадающие списки)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--subsystem",
            default="pilot",
            help="Код подсистемы (по умолчанию pilot)",
        )

    def handle(self, *args, **options):
        sub = Subsystem.objects.filter(code=options["subsystem"]).first()
        if not sub:
            self.stderr.write(f"Подсистема {options['subsystem']} не найдена")
            return
        sync_classifiers_for_subsystem(sub)
        from delayu.models import NSIClassifier

        n = NSIClassifier.objects.filter(subsystem=sub).count()
        self.stdout.write(self.style.SUCCESS(f"Справочников НСИ: {n}"))
