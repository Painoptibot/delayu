"""Sync local MNP store for Krasnodar Krai (features + tiles).

Usage:
  python manage.py sync_mnp_kk
  python manage.py sync_mnp_kk --features-only --limit-schemes=5
  python manage.py sync_mnp_kk --tiles-only --zmax=10
  python manage.py sync_mnp_kk --tiles-only --around-sites --zmin=13 --zmax=15
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from delayu.services.invest_mnp_store import run_sync, store_status


class Command(BaseCommand):
    help = "Синхронизация локального store генплана МНП (только Краснодарский край)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--features-only",
            action="store_true",
            help="Только схемы/фичи из JSP МНП",
        )
        parser.add_argument(
            "--tiles-only",
            action="store_true",
            help="Только PNG-тайлы из WMS МНП",
        )
        parser.add_argument(
            "--limit-schemes",
            type=int,
            default=None,
            help="Ограничить число схем (для демо/CI)",
        )
        parser.add_argument("--zmin", type=int, default=None, help="Мин. zoom тайлов")
        parser.add_argument("--zmax", type=int, default=None, help="Макс. zoom тайлов")
        parser.add_argument(
            "--around-sites",
            action="store_true",
            help="Печь тайлы только вокруг площадок с координатами (для z=13..15)",
        )
        parser.add_argument(
            "--buffer-deg",
            type=float,
            default=None,
            help="Буфер вокруг площадки в градусах (default INVEST_MNP_SITE_TILE_BUFFER_DEG)",
        )

    def handle(self, *args, **options):
        features_only = bool(options["features_only"])
        tiles_only = bool(options["tiles_only"])
        if features_only and tiles_only:
            raise CommandError("Укажите не более одного из --features-only / --tiles-only")
        do_features = not tiles_only
        do_tiles = not features_only
        if features_only:
            do_tiles = False
        if tiles_only:
            do_features = False

        def progress(msg: str) -> None:
            self.stdout.write(msg)

        self.stdout.write("Старт sync_mnp_kk…")
        try:
            run = run_sync(
                features=do_features,
                tiles=do_tiles,
                limit_schemes=options["limit_schemes"],
                zmin=options["zmin"],
                zmax=options["zmax"],
                around_sites=bool(options["around_sites"]),
                buffer_deg=options["buffer_deg"],
                progress=progress,
            )
        except Exception as exc:
            raise CommandError(f"Sync МНП завершился с ошибкой: {exc}") from exc

        status = store_status()
        self.stdout.write(self.style.SUCCESS(
            f"Sync #{run.pk} ok={run.ok} schemes={status['schemes']} "
            f"features={status['features']} tiles={status['tiles']}"
        ))
        self.stdout.write(f"stats={run.stats}")
        if not run.ok:
            raise CommandError(run.error or "Sync failed")
