"""Проверка ключевых URL платформы (запускать при работающем или через Client)."""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.test import Client

User = get_user_model()

URLS = [
    "/auth/login/",
    "/",
    "/cases/",
    "/registries/",
    "/workspace/kanban/",
    "/correspondence/inbox/",
    "/correspondence/outbox/",
    "/correspondence/journal/",
    "/correspondence/signatures/",
    "/correspondence/print-templates/",
    "/bpm/approvals/",
    "/bpm/templates/",
    "/bpm/sla/monitor/",
    "/bpm/regulations/",
    "/chat/",
    "/comms/comments/",
    "/comms/mentions/",
    "/comms/meetings/",
    "/comms/messengers/",
    "/integrations/",
    "/integrations/endpoints/",
    "/integrations/messages/",
    "/integrations/api/",
    "/integrations/smev/",
    "/integrations/external/",
    "/archive/audio/",
    "/ai/",
    "/ai/assistant/",
    "/ai/search/",
    "/ai/tools/",
    "/ai/knowledge/",
    "/ai/policies/",
    "/infra/",
    "/infra/gis/",
    "/infra/pwa/",
    "/infra/sso/",
    "/infra/etl/",
    "/infra/data-hub/",
    "/infra/citizen/",
    "/ops/",
    "/ops/nsi/",
    "/ops/forms/",
    "/ops/bulk/",
    "/ops/exports/",
    "/ops/directives/",
    "/exploit/",
    "/exploit/notifications/",
    "/exploit/antivirus/",
    "/exploit/pii/",
    "/exploit/backups/",
    "/exploit/health/",
    "/exploit/product-passport/",
    "/ux/",
    "/ux/licenses/",
    "/ux/onboarding/",
    "/ux/dashboards/",
    "/ux/marketplace/",
    "/analytics/dashboard/",
    "/analytics/reports/",
    "/analytics/charts/",
    "/analytics/quality/",
    "/analytics/departments/",
    "/administration/subsystems/",
    "/api/v1/health/",
]


class Command(BaseCommand):
    help = "Проверить HTTP 200 на основных страницах (от имени суперпользователя)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            default="",
            help="Логин для проверки (по умолчанию: admin, dalayu или первый superuser)",
        )

    def _pick_user(self, username: str):
        qs = User.objects.filter(is_active=True)
        if username:
            return qs.filter(username=username).first()
        for name in ("admin", "dalayu"):
            user = qs.filter(username=name, is_superuser=True).first()
            if user:
                return user
        return qs.filter(is_superuser=True).order_by("pk").first()

    def handle(self, *args, **options):
        client = Client(HTTP_HOST="127.0.0.1")
        user = self._pick_user(options["username"].strip())
        if not user:
            self.stderr.write(
                "Нет активного superuser. Создайте: python manage.py createsuperuser"
            )
            return
        client.force_login(user)
        self.stdout.write(f"Проверка от имени: {user.username}")
        ok = 0
        fail = 0
        for path in URLS:
            r = client.get(path)
            if r.status_code == 200:
                ok += 1
                self.stdout.write(self.style.SUCCESS(f"OK {path}"))
            else:
                fail += 1
                self.stderr.write(self.style.ERROR(f"FAIL {path} -> {r.status_code}"))
        self.stdout.write(self.style.SUCCESS(f"Готово: {ok} OK, {fail} ошибок"))
