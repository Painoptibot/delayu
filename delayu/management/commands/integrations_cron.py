"""Запуск бесплатных фоновых интеграций (cron). СМЭВ не затрагивается."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.models import Subsystem

User = get_user_model()


class Command(BaseCommand):
    help = "Уведомления УЖВ + очередь webhook + IMAP (если настроен)"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="uzhv")
        parser.add_argument("--all-uzhv", action="store_true")
        parser.add_argument("--skip-mail", action="store_true")
        parser.add_argument(
            "--py07",
            action="store_true",
            help="PY-07: выгрузить JSON payload уведомлений (I-06)",
        )
        parser.add_argument(
            "--no-py07",
            action="store_true",
            help="Не запускать PY-07 (по умолчанию PY-07 включён при --all-uzhv)",
        )

    def handle(self, *args, **options):
        if options["all_uzhv"]:
            subs = Subsystem.objects.filter(industry_template="uzhv")
        else:
            subs = Subsystem.objects.filter(code=options["subsystem"])

        actor = User.objects.filter(is_superuser=True).first()
        for sub in subs:
            self.stdout.write(f"=== {sub.code} ===")
            from delayu.services.uzhv_notifications import sync_uzhv_deadline_notifications

            n = sync_uzhv_deadline_notifications(sub)
            self.stdout.write(f"  уведомления: {n}")

            from delayu.services.integrations import process_pending_queue

            q = process_pending_queue(sub, limit=100)
            self.stdout.write(f"  очередь: {q}")

            if not options["skip_mail"] and actor:
                from delayu.services.mail import sync_inbound_mail

                mail = sync_inbound_mail(sub, user=actor, limit=20)
                self.stdout.write(f"  IMAP: {mail}")

            run_py07 = options["py07"] or (
                options["all_uzhv"] and not options["no_py07"]
            )
            if run_py07:
                from pathlib import Path

                from delayu.services.uzhv_notify_payload import build_notify_payloads

                out = Path("media/uzhv_notify_queue") / sub.code
                py07 = build_notify_payloads(sub, out, days_ahead=5)
                self.stdout.write(f"  PY-07: {py07.count} файлов → {out}")

        self.stdout.write(self.style.SUCCESS("Готово"))
