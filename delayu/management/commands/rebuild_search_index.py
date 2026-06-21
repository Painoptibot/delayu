from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.search_index import rebuild_search_index


class Command(BaseCommand):
    help = "Перестроить поисковый индекс (M48 / pgvector-ready)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="", help="Код подсистемы")

    def handle(self, *args, **options):
        code = (options.get("subsystem") or "").strip()
        qs = Subsystem.objects.all()
        if code:
            qs = qs.filter(code=code)
        for sub in qs:
            stats = rebuild_search_index(sub)
            self.stdout.write(
                self.style.SUCCESS(
                    f"{sub.code}: cases={stats['case']} knowledge={stats['knowledge']} docs={stats['document']}"
                )
            )
