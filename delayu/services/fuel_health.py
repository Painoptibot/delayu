"""Проверка работоспособности контура «Топливный пропуск» и нагрузочное тестирование."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_fuel import FuelApplication, FuelAzsStation, FuelCitizen, FuelEventLog, FuelPermit


def _check_db() -> dict:
    started = time.perf_counter()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        return {"ok": True, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _check_cache() -> dict:
    started = time.perf_counter()
    key = "fuel_health_ping"
    try:
        cache.set(key, "1", 30)
        ok = cache.get(key) == "1"
        return {"ok": ok, "ms": round((time.perf_counter() - started) * 1000, 1)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def fuel_health_report(subsystem: Subsystem) -> dict:
    """Снимок состояния компонентов для демонстрации заказчику."""
    now = timezone.now()
    components = {
        "database": _check_db(),
        "cache": _check_cache(),
    }
    counts = {
        "azs_active": FuelAzsStation.objects.filter(subsystem=subsystem, is_archived=False).count(),
        "citizens": FuelCitizen.objects.filter(subsystem=subsystem).count(),
        "applications_pending": FuelApplication.objects.filter(
            subsystem=subsystem, status=FuelApplication.Status.PENDING
        ).count(),
        "permits_active": FuelPermit.objects.filter(
            subsystem=subsystem,
            status=FuelPermit.Status.ACTIVE,
            valid_until__gte=now,
        ).count(),
        "events_24h": FuelEventLog.objects.filter(
            subsystem=subsystem, created_at__gte=now - timezone.timedelta(hours=24)
        ).count(),
    }
    flags = {
        "debug_mode": bool(getattr(settings, "DEBUG", False)),
        "yandex_maps": bool(getattr(settings, "YANDEX_MAPS_API_KEY", "")),
        "fuel_support_email": bool(getattr(settings, "FUEL_SUPPORT_EMAIL", "")),
    }
    overall = all(c.get("ok") for c in components.values())
    return {
        "ok": overall,
        "checked_at": now.isoformat(),
        "components": components,
        "counts": counts,
        "flags": flags,
    }


def _timed_request(client: Client, path: str, host: str = "127.0.0.1") -> dict:
    started = time.perf_counter()
    try:
        response = client.get(path, HTTP_HOST=host)
        elapsed = (time.perf_counter() - started) * 1000
        return {
            "path": path,
            "status": response.status_code,
            "ms": round(elapsed, 1),
            "ok": response.status_code < 500,
        }
    except Exception as exc:
        return {"path": path, "status": 0, "ms": 0, "ok": False, "error": str(exc)}


def run_load_demo(
    subsystem: Subsystem,
    *,
    requests_per_endpoint: int = 20,
    workers: int = 8,
) -> dict:
    """Эмуляция параллельных запросов к публичным и операторским API."""
    slug = subsystem.public_subdomain or subsystem.code
    portal_root = f"/fuel/{slug}/"
    endpoints = [
        portal_root,
        f"{portal_root}status.json",
        f"{portal_root}status.json?refresh=1",
    ]
    try:
        endpoints.append(reverse("fuel-operator-metrics-api"))
    except Exception:
        pass

    client = Client()
    host = "127.0.0.1"
    jobs = []
    for path in endpoints:
        for _ in range(requests_per_endpoint):
            jobs.append(path)

    results: list[dict] = []
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_timed_request, client, path, host) for path in jobs]
        for fut in as_completed(futures):
            results.append(fut.result())

    total_ms = (time.perf_counter() - started) * 1000
    ok_count = sum(1 for r in results if r.get("ok"))
    latencies = sorted(r["ms"] for r in results if r.get("ms"))
    p95 = latencies[int(len(latencies) * 0.95) - 1] if latencies else 0
    by_path: dict[str, list[float]] = {}
    for row in results:
        by_path.setdefault(row["path"], []).append(row["ms"])
    per_endpoint = {
        path: {
            "count": len(vals),
            "avg_ms": round(sum(vals) / len(vals), 1) if vals else 0,
            "max_ms": round(max(vals), 1) if vals else 0,
        }
        for path, vals in by_path.items()
    }
    return {
        "ok": ok_count == len(results),
        "total_requests": len(results),
        "success_count": ok_count,
        "error_count": len(results) - ok_count,
        "duration_ms": round(total_ms, 1),
        "rps": round(len(results) / (total_ms / 1000), 1) if total_ms else 0,
        "p95_ms": round(p95, 1),
        "per_endpoint": per_endpoint,
        "sample_errors": [r for r in results if not r.get("ok")][:5],
    }
