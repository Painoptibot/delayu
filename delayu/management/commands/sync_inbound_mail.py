"""Синхронизация входящей почты по IMAP для подсистем."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.models import Subsystem
from delayu.services.mail import sync_inbound_mail

User = get_user_model()


class Command(BaseCommand):
    help = "Забрать новые письма по IMAP и зарегистрировать как входящую корреспонденцию"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", type=str, help="Код подсистемы")
        parser.add_argument("--limit", type=int, default=30)

    def handle(self, *args, **options):
        qs = Subsystem.objects.all()
        code = options.get("subsystem")
        if code:
            qs = qs.filter(code=code)
        actor = User.objects.filter(is_superuser=True).first()
        if not actor:
            self.stderr.write("Нет суперпользователя для регистрации писем.")
            return
        for sub in qs:
            result = sync_inbound_mail(sub, user=actor, limit=options["limit"])
            self.stdout.write(f"{sub.code}: {result}")
