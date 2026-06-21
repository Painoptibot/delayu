"""Django management command: установка pgvector на Windows."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Скачать и установить pgvector для PostgreSQL 18 (Windows, UAC)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-password",
            default="",
            help="Пароль суперпользователя postgres (иначе запросит интерактивно)",
        )

    def handle(self, *args, **options):
        import os
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        script = root / "scripts" / "setup_pgvector.py"
        env = os.environ.copy()
        if options["admin_password"]:
            env["POSTGRES_ADMIN_PASSWORD"] = options["admin_password"]
        code = subprocess.call([sys.executable, str(script)], cwd=root, env=env)
        if code:
            self.stderr.write(self.style.ERROR("Установка pgvector не завершена."))
        else:
            self.stdout.write(self.style.SUCCESS("pgvector установлен и проиндексирован."))
