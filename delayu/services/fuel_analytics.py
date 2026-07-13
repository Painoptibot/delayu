"""Аналитика и дашборд «Топливный пропуск» — 15 метрик."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_fuel import (
    FuelApplication,
    FuelAzsStation,
    FuelBlacklistEntry,
    FuelCategory,
    FuelPermit,
    FuelRedeem,
    FuelRedeemAttempt,
)
from delayu.services.fuel import normalize_plate, normalize_inn

# Центр Новороссийска для карты по умолчанию
NOVOROSSIYSK_CENTER = [44.723, 37.768]


def _azs_status_color(status: str) -> str:
    return {
        FuelAzsStation.Status.OK: "#22c55e",
        FuelAzsStation.Status.LOW: "#eab308",
        FuelAzsStation.Status.BUSY: "#f97316",
        FuelAzsStation.Status.EMPTY: "#ef4444",
    }.get(status, "#64748b")


def azs_map_points(subsystem: Subsystem) -> list[dict]:
    from delayu.services.fuel_capacity import azs_capacity_snapshot, get_portal_settings

    settings = get_portal_settings(subsystem)
    points = []
    for azs in subsystem.fuel_azs_stations.filter(is_archived=False):
        if azs.latitude is None or azs.longitude is None:
            continue
        cap = azs_capacity_snapshot(azs, settings)
        points.append(
            {
                "lat": float(azs.latitude),
                "lng": float(azs.longitude),
                "title": azs.name,
                "address": azs.address,
                "badge": (
                    f"~{cap['queue_minutes_computed']} мин · {azs.stock_liters} л · "
                    f"заявок {cap['apps_submitted']}/{cap['max_applications']}"
                ),
                "color": _azs_status_color(azs.status),
                "district": azs.district,
                "status": azs.get_status_display(),
                "accepting": azs.is_accepting_permits,
                "apps_submitted": cap["apps_submitted"],
                "apps_redeemed_today": cap["apps_redeemed_today"],
                "apps_remaining": cap["apps_remaining"],
                "max_applications": cap["max_applications"],
                "queue_minutes": cap["queue_minutes_computed"],
                "stock_liters": azs.stock_liters,
            }
        )
    return points


def _district_stress(azs_list: list[FuelAzsStation]) -> tuple[int, str]:
    """Индекс проблемности 0–100 и цвет."""
    if not azs_list:
        return 0, "ok"
    empty = sum(1 for a in azs_list if a.status == FuelAzsStation.Status.EMPTY)
    busy = sum(1 for a in azs_list if a.status == FuelAzsStation.Status.BUSY)
    avg_queue = sum(a.queue_minutes for a in azs_list) / len(azs_list)
    score = min(100, int(empty * 25 + busy * 15 + avg_queue * 0.8))
    if score >= 60:
        return score, "critical"
    if score >= 30:
        return score, "warn"
    return score, "ok"


def full_dashboard_metrics(subsystem: Subsystem) -> dict:
    today = timezone.localdate()
    now = timezone.now()
    hour_ago = now - timezone.timedelta(hours=1)

    stations = list(subsystem.fuel_azs_stations.all())
    redeems_today = FuelRedeem.objects.filter(subsystem=subsystem, created_at__date=today)
    attempts_today = FuelRedeemAttempt.objects.filter(subsystem=subsystem, created_at__date=today)
    apps_today = FuelApplication.objects.filter(subsystem=subsystem, created_at__date=today)
    permits_active = FuelPermit.objects.filter(
        subsystem=subsystem,
        status=FuelPermit.Status.ACTIVE,
        valid_until__gte=now,
        remaining_liters__gt=0,
    )

    # 1 — средняя очередь
    avg_queue = (
        sum(s.queue_minutes for s in stations) / len(stations) if stations else 0
    )

    # 2 — районы
    by_district: dict[str, list] = defaultdict(list)
    for s in stations:
        key = s.district or "Без района"
        by_district[key].append(s)
    districts = []
    for name, azs_list in by_district.items():
        score, level = _district_stress(azs_list)
        districts.append(
            {
                "name": name,
                "score": score,
                "level": level,
                "azs_count": len(azs_list),
                "empty_count": sum(1 for a in azs_list if a.status == FuelAzsStation.Status.EMPTY),
                "avg_queue": round(sum(a.queue_minutes for a in azs_list) / len(azs_list), 1)
                if azs_list
                else 0,
            }
        )
    districts.sort(key=lambda d: -d["score"])

    # 3–6 — по АЗС
    from delayu.services.fuel_capacity import azs_capacity_snapshot, get_portal_settings

    portal_settings = get_portal_settings(subsystem)
    azs_rows = []
    for s in stations:
        cap = azs_capacity_snapshot(s, portal_settings)
        hours_left = (
            round(s.stock_liters / max(1, portal_settings.permit_quota_liters) / max(1, cap["queue_minutes_computed"] / 15 + 1), 1)
            if s.stock_liters
            else 0
        )
        directed = permits_active.filter(assigned_azs=s).count()
        azs_rows.append(
            {
                "station": s,
                "hours_left": hours_left,
                "directed_permits": directed,
                "redeems_today": redeems_today.filter(azs=s).count(),
                "liters_today": redeems_today.filter(azs=s).aggregate(s=Sum("liters"))["s"] or 0,
                "apps_submitted": cap["apps_submitted"],
                "apps_remaining": cap["apps_remaining"],
                "max_applications": cap["max_applications"],
                "queue_computed": cap["queue_minutes_computed"],
            }
        )

    # 7 — отказы
    denials_today = attempts_today.filter(success=False).count()

    # 8 — крупные отпуски
    large_alerts = list(
        redeems_today.filter(liters__gt=30).values("plate", "azs__name", "liters", "created_at")[:20]
    )

    # 9 — выдано vs отпущено
    issued_today = permits_active.filter(created_at__date=today).count()
    redeemed_count = redeems_today.count()
    gap_pct = 0
    if issued_today:
        gap_pct = round(max(0, 100 - (redeemed_count / issued_today * 100)), 1)

    # 10 — заявки по категориям
    apps_by_category = (
        apps_today.values("category__name", "category__code")
        .annotate(c=Count("id"))
        .order_by("-c")
    )

    # 11 — литры по категориям
    liters_by_category = []
    for cat in FuelCategory.objects.filter(subsystem=subsystem):
        liters = (
            redeems_today.filter(permit__category=cat).aggregate(s=Sum("liters"))["s"] or 0
        )
        liters_by_category.append({"category": cat.name, "code": cat.code, "liters": liters})

    # 12 — топ перегруженных / недогруженных
    overloaded = sorted(stations, key=lambda s: -s.queue_minutes)[:5]
    underloaded = sorted(
        [s for s in stations if s.is_accepting_permits and s.status == FuelAzsStation.Status.OK],
        key=lambda s: s.queue_minutes,
    )[:5]

    # 13 — активные пропуска по АЗС (уже в azs_rows as directed_permits)

    # 14 — подозрительные: 3+ АЗС за час
    suspicious = []
    recent = redeems_today.filter(created_at__gte=hour_ago)
    plate_azs: dict[str, set] = defaultdict(set)
    for r in recent:
        plate_azs[r.plate].add(r.azs_id)
    for plate, azs_ids in plate_azs.items():
        if len(azs_ids) >= 3:
            suspicious.append({"plate": plate, "azs_count": len(azs_ids)})

    # 15 — реакция на низкий остаток (упрощённо: мин с последнего обновления LOW/EMPTY)
    low_stations = [s for s in stations if s.status in (FuelAzsStation.Status.LOW, FuelAzsStation.Status.EMPTY)]
    response_min = None
    if low_stations:
        oldest = min(s.updated_at for s in low_stations)
        response_min = int((now - oldest).total_seconds() / 60)

    return {
        "updated_at": now,
        "avg_queue_minutes": round(avg_queue, 1),
        "districts": districts,
        "azs_rows": azs_rows,
        "empty_azs_count": sum(1 for s in stations if s.status == FuelAzsStation.Status.EMPTY),
        "denials_today": denials_today,
        "large_alerts": large_alerts,
        "permits_issued_today": issued_today,
        "redeems_today": redeemed_count,
        "gap_pct": gap_pct,
        "apps_by_category": list(apps_by_category),
        "liters_by_category": liters_by_category,
        "overloaded": overloaded,
        "underloaded": underloaded,
        "suspicious": suspicious,
        "response_minutes": response_min,
        "map_points": azs_map_points(subsystem),
        "map_center": NOVOROSSIYSK_CENTER,
        "pending_apps": FuelApplication.objects.filter(
            subsystem=subsystem, status=FuelApplication.Status.PENDING
        ).count(),
        "liters_today_total": redeems_today.aggregate(s=Sum("liters"))["s"] or 0,
    }


def leadership_metrics(subsystem: Subsystem) -> dict:
    """Упрощённые метрики для экрана руководства (UI-3)."""
    from django.db.models.functions import TruncHour

    base = full_dashboard_metrics(subsystem)
    since = timezone.now() - timezone.timedelta(hours=24)
    hourly_raw = (
        FuelRedeem.objects.filter(subsystem=subsystem, created_at__gte=since)
        .annotate(bucket=TruncHour("created_at"))
        .values("bucket")
        .annotate(count=Count("id"), liters=Sum("liters"))
        .order_by("bucket")
    )
    hourly = [
        {
            "hour": row["bucket"].strftime("%H:%M") if row["bucket"] else "",
            "count": row["count"],
            "liters": float(row["liters"] or 0),
        }
        for row in hourly_raw
    ]
    max_count = max((h["count"] for h in hourly), default=1) or 1
    for h in hourly:
        h["bar_pct"] = round(h["count"] / max_count * 100)

    return {
        "updated_at": base["updated_at"],
        "districts": base["districts"],
        "avg_queue_minutes": base["avg_queue_minutes"],
        "pending_apps": base["pending_apps"],
        "liters_today_total": base["liters_today_total"],
        "denials_today": base["denials_today"],
        "empty_azs_count": base["empty_azs_count"],
        "redeems_today": base["redeems_today"],
        "gap_pct": base["gap_pct"],
        "hourly_redeems": hourly,
        "map_points_json": base["map_points"],
    }


def log_redeem_attempt(
    subsystem: Subsystem,
    *,
    azs: FuelAzsStation | None = None,
    plate: str = "",
    success: bool,
    error_code: str = "",
    liters: Decimal | None = None,
) -> None:
    FuelRedeemAttempt.objects.create(
        subsystem=subsystem,
        azs=azs,
        plate=normalize_plate(plate) if plate else "",
        success=success,
        error_code=error_code,
        liters=liters,
    )


def add_blacklist_entry(
    subsystem: Subsystem, *, plate: str = "", inn: str = "", reason: str
) -> FuelBlacklistEntry:
    plate_n = normalize_plate(plate) if plate else ""
    inn_s = normalize_inn(inn) if inn else ""
    if not plate_n and not inn_s:
        raise ValueError("Укажите госномер или ИНН")
    return FuelBlacklistEntry.objects.create(
        subsystem=subsystem,
        plate=plate_n,
        inn=inn_s,
        reason=reason.strip() or "Без указания причины",
        is_active=True,
    )
