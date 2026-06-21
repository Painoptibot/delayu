from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import Subsystem
from delayu.services.retention import purge_expired_cases


class Command(BaseCommand):
    help = "Удалить архивные дела с истёкшим сроком хранения (M06, без legal hold)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="", help="Код подсистемы")
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Выполнить удаление (по умолчанию dry-run)",
        )

    def handle(self, *args, **options):
        code = (options.get("subsystem") or "").strip()
        dry_run = not options.get("execute")
        subs = filter_subsystems(Subsystem.objects.all(), code, stdout=self.stdout, style=self.style)
        if subs is None:
            return
        if not subs:
            self.stderr.write(self.style.ERROR("В базе нет подсистем. Запустите: manage.bat seed_demo"))
            return
        for sub in subs:
            result = purge_expired_cases(sub, dry_run=dry_run)
            mode = "DRY-RUN" if result.get("dry_run") else "DONE"
            self.stdout.write(
                self.style.WARNING(f"[{mode}] {sub.code}: count={result['count']} sample={result.get('sample', [])}")
            )
