"""Включить pgvector и синхронизировать embedding_vec."""
from django.core.management.base import BaseCommand

from delayu.management.subsystem_cli import filter_subsystems
from delayu.models import SearchIndexEntry, Subsystem
from delayu.services.pgvector_search import ensure_pgvector_schema, pgvector_available, sync_entry_vector
from delayu.services.search_index import rebuild_search_index


class Command(BaseCommand):
    help = "CREATE EXTENSION vector + колонка embedding_vec + синхронизация индекса"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="", help="Код подсистемы для rebuild")
        parser.add_argument("--rebuild", action="store_true", help="Пересобрать JSON-эмбеддинги")

    def handle(self, *args, **options):
        ok = ensure_pgvector_schema()
        if not ok:
            self.stderr.write(
                self.style.WARNING(
                    "pgvector недоступен: нужен PostgreSQL и расширение vector "
                    "(CREATE EXTENSION vector; от суперпользователя postgres)."
                )
            )
            self.stderr.write(
                self.style.WARNING(
                    "На Windows: установите pgvector для вашей версии PG "
                    "(https://github.com/pgvector/pgvector#installation). "
                    "Без него семантический поиск работает через JSON-эмбеддинги в Python."
                )
            )
            return
        self.stdout.write(self.style.SUCCESS("pgvector: схема готова"))
        if options["rebuild"]:
            code = (options["subsystem"] or "").strip()
            subs = filter_subsystems(Subsystem.objects.all(), code, stdout=self.stdout, style=self.style)
            if subs is None:
                return
            for sub in subs or []:
                stats = rebuild_search_index(sub)
                self.stdout.write(f"  {sub.code}: {stats}")
        if pgvector_available():
            synced = 0
            for entry in SearchIndexEntry.objects.exclude(embedding=[]).iterator():
                sync_entry_vector(entry.pk, entry.embedding)
                synced += 1
            self.stdout.write(self.style.SUCCESS(f"Синхронизировано векторов: {synced}"))
