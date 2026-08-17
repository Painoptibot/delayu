# -*- coding: utf-8 -*-
"""Сидер АЗС ЮФО + mock-сигналы наличия топлива."""
from __future__ import annotations

import zlib

from django.core.management.base import BaseCommand
from django.utils import timezone

from delayu.data.fuel_ufo_azs import as_dicts
from delayu.models_fuel_ufo import (
    FuelUfoAvailability as Av,
    FuelUfoAzsPoint,
    FuelUfoDataSource,
    FuelUfoRegion,
    FuelUfoRegionBanner,
)
from delayu.services import fuel_ufo as svc


def _status(code: str, grade: str) -> str:
    """Разный, но стабильный статус — карта должна выглядеть как живая, не как демо-сетка."""
    n = zlib.crc32(f"{code}:{grade}".encode("utf-8")) % 10
    if "empty" in code or code.endswith("dzerzh-227"):
        return Av.EMPTY
    if n <= 5:
        return Av.OK
    if n <= 8:
        return Av.LOW
    return Av.EMPTY


class Command(BaseCommand):
    help = "Seed UFO AZS points + mock bank observations + region banners"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Перезаписать каталог, даже если точки уже есть",
        )

    def handle(self, *args, **options):
        if FuelUfoAzsPoint.objects.exists() and not options.get("force"):
            self.stdout.write(
                f"Каталог ЮФО уже есть ({FuelUfoAzsPoint.objects.count()} точек). "
                "Пропуск. Обновить: manage.py seed_fuel_ufo --force"
            )
            return
        created = 0
        rows = as_dicts()
        for row in rows:
            obj, was_created = FuelUfoAzsPoint.objects.update_or_create(
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "network": row["network"],
                    "address": row["address"],
                    "region": row["region"],
                    "city": row["city"],
                    "latitude": row["lat"],
                    "longitude": row["lon"],
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
            svc.ingest_partner_mock(obj, FuelUfoDataSource.SBER, "ai95", _status(row["code"], "ai95"))
            svc.ingest_partner_mock(obj, FuelUfoDataSource.TBANK, "ai92", _status(row["code"], "ai92"))
            svc.ingest_partner_mock(obj, FuelUfoDataSource.SBER, "diesel", _status(row["code"], "diesel"))
            snap = svc.recompute_snapshot(obj)
            n = zlib.crc32(row["code"].encode("utf-8"))
            snap.queue_minutes = (n % 7) * 5 or None
            snap.traffic_jams = 2 + (n % 7)
            snap.traffic_fetched_at = timezone.now()
            snap.save(update_fields=["queue_minutes", "traffic_jams", "traffic_fetched_at"])

        banners = [
            (
                FuelUfoRegion.KRASNODAR,
                "В крае действуют лимиты на АЗС",
                "В Новороссийске, Краснодаре и на побережье сети вводят лимиты 20–40 л. Смотрите свежесть статуса перед выездом.",
            ),
            (
                FuelUfoRegion.ROSTOV,
                "Ростовская область: очереди на популярных АЗС",
                "Сообщайте фактическую ситуацию — так водителям рядом не нужно ехать впустую.",
            ),
            (
                FuelUfoRegion.CRIMEA,
                "Крым: проверяйте наличие перед поездкой",
                "На полуострове данные обновляются медленнее. Если вы на месте — нажмите «Есть / Мало / Нет».",
            ),
        ]
        for region, title, body in banners:
            FuelUfoRegionBanner.objects.update_or_create(
                region=region,
                defaults={"title": title, "body": body, "is_active": True},
            )
        keep = {row["code"] for row in rows}
        deactivated = FuelUfoAzsPoint.objects.exclude(code__in=keep).update(is_active=False)
        self.stdout.write(
            self.style.SUCCESS(
                f"UFO seed OK: points={FuelUfoAzsPoint.objects.filter(is_active=True).count()} "
                f"catalog={len(rows)} new={created} deactivated={deactivated}"
            )
        )
