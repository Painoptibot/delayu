"""Бизнес-логика «Топливный пропуск»."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Max, Sum
from django.utils import timezone

from delayu.models_fuel import (
    FuelApplication,
    FuelAzsStation,
    FuelBlacklistEntry,
    FuelCategory,
    FuelCitizen,
    FuelParityRule,
    FuelPermit,
    FuelRedeem,
)
from delayu.models import Subsystem

PLATE_RE = re.compile(r"^[АВЕКМНОРСТУХABEKMHOPCTYX]\d{3}[АВЕКМНОРСТУХABEKMHOPCTYX]{2}\d{2,3}$", re.I)
CYR_TO_LAT = str.maketrans("АВЕКМНОРСТУХ", "ABEKMHOPCTYX")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    return digits


def format_phone_display(phone: str) -> str:
    p = normalize_phone(phone)
    if len(p) == 11:
        return f"+7 ({p[1:4]}) {p[4:7]}-{p[7:9]}-{p[9:11]}"
    return phone


def normalize_plate(raw: str) -> str:
    plate = (raw or "").upper().replace(" ", "")
    plate = plate.translate(CYR_TO_LAT)
    return plate


def validate_plate(raw: str) -> bool:
    plate = normalize_plate(raw)
    return bool(plate and PLATE_RE.match(plate))


def normalize_inn(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def validate_inn(raw: str) -> bool:
    """ИНН юрлица (10 цифр) или физлица/ИП (12 цифр) с контрольной суммой."""
    inn = normalize_inn(raw)
    if not inn.isdigit():
        return False
    if len(inn) == 10:
        weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        check = sum(int(inn[i]) * weights[i] for i in range(9)) % 11 % 10
        return check == int(inn[9])
    if len(inn) == 12:
        w11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        w12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c11 = sum(int(inn[i]) * w11[i] for i in range(10)) % 11 % 10
        c12 = sum(int(inn[i]) * w12[i] for i in range(11)) % 11 % 10
        return c11 == int(inn[10]) and c12 == int(inn[11])
    return False


def resolve_fuel_subsystem(
    *,
    host: str = "",
    path_subdomain: str = "",
) -> Subsystem | None:
    """Найти подсистему по поддомену или slug в пути."""
    slug = (path_subdomain or "").strip().lower()
    if not slug and host:
        base = (getattr(settings, "FUEL_PLATFORM_BASE_DOMAIN", "") or "").strip().lower()
        host_only = host.split(":")[0].lower()
        if base and host_only.endswith("." + base):
            slug = host_only[: -(len(base) + 1)].split(".")[0]
        elif host_only not in ("localhost", "127.0.0.1") and "." in host_only:
            slug = host_only.split(".")[0]
    if not slug:
        return None
    return (
        Subsystem.objects.filter(
            public_subdomain=slug,
            industry_template="fuel",
            status=Subsystem.Status.ACTIVE,
        )
        .first()
    )


def citizen_session_key(subsystem_id: int) -> str:
    return f"fuel_citizen_{subsystem_id}"


def get_session_citizen(request, subsystem: Subsystem) -> FuelCitizen | None:
    pk = request.session.get(citizen_session_key(subsystem.pk))
    if not pk:
        return None
    return FuelCitizen.objects.filter(pk=pk, subsystem=subsystem).first()


def login_citizen(
    request,
    subsystem: Subsystem,
    phone: str,
    full_name: str,
    *,
    max_chat_id: str = "",
    pd_consent: bool = False,
    auth_source: str = "otp",
) -> FuelCitizen:
    phone_n = normalize_phone(phone)
    citizen, _ = FuelCitizen.objects.get_or_create(
        subsystem=subsystem,
        phone=phone_n,
        defaults={"full_name": full_name.strip()},
    )
    updated = []
    if full_name.strip() and citizen.full_name != full_name.strip():
        citizen.full_name = full_name.strip()
        updated.append("full_name")
    if max_chat_id.strip() and citizen.max_chat_id != max_chat_id.strip():
        citizen.max_chat_id = max_chat_id.strip()
        updated.append("max_chat_id")
    if pd_consent and not citizen.pd_consent_at:
        citizen.pd_consent_at = timezone.now()
        updated.append("pd_consent_at")
    if updated:
        updated.append("updated_at")
        citizen.save(update_fields=updated)
    request.session[citizen_session_key(subsystem.pk)] = citizen.pk
    request.session.modified = True
    from delayu.models_fuel import FuelEventLog
    from delayu.services.fuel_events import log_fuel_event

    log_fuel_event(
        subsystem,
        FuelEventLog.Channel.CITIZEN,
        "citizen.login",
        f"Вход в портал ({auth_source}) · {format_phone_display(phone_n) or phone_n}",
        citizen=citizen,
        request=request,
        payload={"source": auth_source, "phone": phone_n},
    )
    return citizen


def logout_citizen(request, subsystem: Subsystem) -> None:
    from delayu.models_fuel import FuelEventLog
    from delayu.services.fuel_events import log_fuel_event

    citizen = get_session_citizen(request, subsystem)
    if citizen:
        log_fuel_event(
            subsystem,
            FuelEventLog.Channel.CITIZEN,
            "citizen.logout",
            f"Выход из портала · {citizen.full_name or citizen.phone}",
            citizen=citizen,
            request=request,
        )
    request.session.pop(citizen_session_key(subsystem.pk), None)
    request.session.modified = True


def next_application_number(subsystem: Subsystem) -> str:
    today = timezone.localdate()
    prefix = f"НВР-{today.strftime('%y%m%d')}"
    count = FuelApplication.objects.filter(
        subsystem=subsystem, number__startswith=prefix
    ).count()
    return f"{prefix}-{count + 1:04d}"


def next_permit_number() -> str:
    today = timezone.localdate()
    prefix = f"ТП-{today.strftime('%y%m%d')}"
    count = FuelPermit.objects.filter(number__startswith=prefix).count()
    return f"{prefix}-{count + 1:05d}"


def is_blacklisted(subsystem: Subsystem, *, plate: str = "", inn: str = "") -> bool:
    plate_n = normalize_plate(plate)
    qs = FuelBlacklistEntry.objects.filter(subsystem=subsystem, is_active=True)
    if plate_n and qs.filter(plate=plate_n).exists():
        return True
    if inn and qs.filter(inn=normalize_inn(inn)).exists():
        return True
    return False


def _plate_last_digit(plate: str) -> int | None:
    plate_n = normalize_plate(plate)
    for ch in reversed(plate_n):
        if ch.isdigit():
            return int(ch)
    return None


def plate_parity_rule_today(subsystem: Subsystem, on_date=None) -> dict | None:
    """Правило чёт/нечёт для подсистемы (портал и валидация заявок)."""
    return resolve_parity_rule(subsystem, on_date=on_date)


def _default_parity_message(day, allowed_parity: str) -> str:
    label = "чётные" if allowed_parity == "even" else "нечётные"
    return (
        f"{day.strftime('%d.%m.%Y')}: на АЗС допускаются только {label} госномера "
        "(по последней цифре номера)."
    )


def resolve_parity_rule(subsystem: Subsystem, on_date=None) -> dict | None:
    if not getattr(settings, "FUEL_PLATE_PARITY_ENABLED", True):
        return None
    rule = FuelParityRule.objects.filter(subsystem=subsystem).first()
    if rule and not rule.is_enabled:
        return None

    day = on_date or timezone.localdate()
    mode = rule.mode if rule else FuelParityRule.Mode.CALENDAR
    if mode == FuelParityRule.Mode.CALENDAR:
        even_day = day.day % 2 == 0
        allowed_parity = "even" if even_day else "odd"
    elif mode == FuelParityRule.Mode.EVEN:
        even_day = True
        allowed_parity = "even"
    else:
        even_day = False
        allowed_parity = "odd"

    message = (rule.message.strip() if rule and rule.message else "") or _default_parity_message(
        day, allowed_parity
    )
    label = "чётные" if allowed_parity == "even" else "нечётные"
    updated = rule.updated_at.isoformat() if rule else day.isoformat()
    version = hashlib.sha256(
        f"{subsystem.pk}:{updated}:{day.isoformat()}:{message}".encode()
    ).hexdigest()[:16]

    return {
        "even_day": even_day,
        "allowed_parity": allowed_parity,
        "title": "Сегодня — " + label + " номера",
        "message": message,
        "version": version,
    }


def get_or_create_parity_rule(subsystem: Subsystem) -> FuelParityRule:
    rule, _ = FuelParityRule.objects.get_or_create(subsystem=subsystem)
    return rule


def save_parity_rule(
    subsystem: Subsystem,
    *,
    is_enabled: bool,
    mode: str,
    message: str = "",
) -> FuelParityRule:
    rule = get_or_create_parity_rule(subsystem)
    rule.is_enabled = is_enabled
    rule.mode = mode
    rule.message = message.strip()
    rule.save(update_fields=["is_enabled", "mode", "message", "updated_at"])
    return rule


def plate_parity_allows(
    plate: str, subsystem: Subsystem, on_date=None
) -> tuple[bool, str]:
    rule = resolve_parity_rule(subsystem, on_date=on_date)
    if not rule:
        return True, ""
    digit = _plate_last_digit(plate)
    if digit is None:
        return True, ""
    is_even = digit % 2 == 0
    allowed = is_even if rule["allowed_parity"] == "even" else not is_even
    if allowed:
        return True, ""
    want = "чётную" if rule["allowed_parity"] == "even" else "нечётную"
    return False, f"Сегодня разрешены только {want} последнюю цифру госномера."


def taxi_window_warning(category: FuelCategory) -> str | None:
    """Окно подачи заявок для такси (категория III)."""
    if category.code != "III":
        return None
    now = timezone.localtime()
    start_h = getattr(settings, "FUEL_TAXI_WINDOW_START", 6)
    end_h = getattr(settings, "FUEL_TAXI_WINDOW_END", 22)
    if now.hour < start_h or now.hour >= end_h:
        return f"Категория «{category.name}»: заявки принимаются с {start_h:02d}:00 до {end_h:02d}:00."
    return None


def portal_public_banners(subsystem: Subsystem) -> list[dict]:
    banners = []
    parity = resolve_parity_rule(subsystem)
    if parity:
        banners.append({"kind": "parity", **parity})
    return banners


def liters_redeemed_today(subsystem: Subsystem, plate: str) -> Decimal:
    plate_n = normalize_plate(plate)
    start = timezone.localdate()
    total = (
        FuelRedeem.objects.filter(
            subsystem=subsystem,
            plate=plate_n,
            created_at__date=start,
        ).aggregate(s=Sum("liters"))["s"]
        or 0
    )
    return Decimal(total)


def fuel_brand_short(subsystem) -> str:
    """Короткий заголовок для шапки портала (без дублирования подзаголовка)."""
    name = (getattr(subsystem, "name", None) or "").strip()
    if "—" in name:
        city = name.split("—", 1)[0].strip()
        return f"Топливный пропуск · {city}"
    if len(name) > 36:
        return "Топливный пропуск"
    if name and "топлив" not in name.lower():
        return f"Топливный пропуск · {name}"
    return "Топливный пропуск"


def suggest_redeem_liters(permit: FuelPermit) -> Decimal:
    """Рекомендуемый объём отпуска с учётом остатка, суточного лимита и заявки жителя."""
    daily = Decimal(permit.category.daily_limit_liters)
    redeemed_today = liters_redeemed_today(permit.subsystem, permit.plate)
    daily_remaining = max(Decimal(0), daily - redeemed_today)
    permit_remaining = Decimal(permit.remaining_liters)
    cap = min(permit_remaining, daily_remaining)
    requested = getattr(permit.application, "requested_liters", None)
    if requested:
        return min(cap, Decimal(requested))
    return cap


def recommend_azs(subsystem: Subsystem, limit: int = 3) -> list[FuelAzsStation]:
    qs = (
        FuelAzsStation.objects.filter(
            subsystem=subsystem,
            is_accepting_permits=True,
            is_archived=False,
        )
        .exclude(status=FuelAzsStation.Status.EMPTY)
        .order_by("queue_minutes", "-stock_liters")
    )
    return list(qs[:limit])


def _sign_payload(payload: dict) -> str:
    secret = (settings.SECRET_KEY or "dev").encode()
    body = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hmac.new(secret, body.encode(), hashlib.sha256).hexdigest()


def build_qr_payload(permit: FuelPermit) -> str:
    payload = {
        "v": 1,
        "pid": permit.pk,
        "num": permit.number,
        "plate": permit.plate,
        "max": permit.max_liters,
        "rem": permit.remaining_liters,
        "until": permit.valid_until.isoformat(),
        "sub": permit.subsystem_id,
    }
    sig = _sign_payload(payload)
    return json.dumps({**payload, "sig": sig}, ensure_ascii=False)


def verify_qr_payload(raw: str) -> tuple[dict | None, str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None, "INVALID_JSON"
    sig = data.pop("sig", "")
    expected = _sign_payload(data)
    if not hmac.compare_digest(sig, expected):
        return None, "INVALID_SIGNATURE"
    return data, ""


@transaction.atomic
def create_application(
    *,
    subsystem: Subsystem,
    citizen: FuelCitizen,
    category: FuelCategory,
    plate: str,
    vehicle_make: str = "",
    inn: str = "",
    org_name: str = "",
    preferred_azs: FuelAzsStation | None = None,
    requested_liters: int | None = None,
) -> FuelApplication:
    plate_n = normalize_plate(plate)
    if not validate_plate(plate_n):
        raise ValueError("Некорректный госномер")
    if is_blacklisted(subsystem, plate=plate_n, inn=inn):
        raise ValueError("Госномер или ИНН в чёрном списке")

    parity_ok, parity_msg = plate_parity_allows(plate_n, subsystem)
    if not parity_ok:
        raise ValueError(parity_msg)

    taxi_msg = taxi_window_warning(category)
    if taxi_msg:
        raise ValueError(taxi_msg)

    daily_limit = category.daily_limit_liters
    redeemed = liters_redeemed_today(subsystem, plate_n)
    if redeemed >= daily_limit:
        raise ValueError("Суточный лимит по этому госномеру уже исчерпан")

    if preferred_azs:
        assigned_azs = preferred_azs
    else:
        recommended = recommend_azs(subsystem, limit=1)
        assigned_azs = recommended[0] if recommended else None

    status = (
        FuelApplication.Status.PENDING
        if category.requires_moderation
        else FuelApplication.Status.APPROVED
    )

    req_liters = None
    if requested_liters is not None and requested_liters > 0:
        req_liters = min(int(requested_liters), int(daily_limit))

    app = FuelApplication.objects.create(
        subsystem=subsystem,
        citizen=citizen,
        number=next_application_number(subsystem),
        category=category,
        plate=plate_n,
        vehicle_make=vehicle_make.strip(),
        inn=inn.strip(),
        org_name=org_name.strip(),
        status=status,
        assigned_azs=assigned_azs,
        requested_liters=req_liters,
    )

    if status == FuelApplication.Status.APPROVED:
        approve_application(app, auto=True)

    from delayu.services.fuel_events import log_fuel_event

    log_fuel_event(
        subsystem,
        "citizen",
        "application.create",
        f"Подана заявка {app.number} · {plate_n}",
        citizen=citizen,
        object_type="FuelApplication",
        object_id=app.pk,
        payload={"status": app.status, "category": category.code},
    )
    if assigned_azs:
        from delayu.services.fuel_capacity import refresh_azs_queue

        refresh_azs_queue(assigned_azs)
    return app


@transaction.atomic
def approve_application(application: FuelApplication, *, auto: bool = False) -> FuelPermit:
    if application.status == FuelApplication.Status.APPROVED and hasattr(application, "permit"):
        return application.permit

    application.status = FuelApplication.Status.APPROVED
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reviewed_at"])

    limit = application.category.daily_limit_liters
    redeemed = liters_redeemed_today(application.subsystem, application.plate)
    remaining = max(0, limit - int(redeemed))

    permit = FuelPermit.objects.create(
        subsystem=application.subsystem,
        application=application,
        number=next_permit_number(),
        plate=application.plate,
        category=application.category,
        max_liters=limit,
        remaining_liters=remaining,
        assigned_azs=application.assigned_azs,
        valid_until=timezone.now() + timedelta(days=1),
        manual_code=hashlib.sha256(application.number.encode()).hexdigest()[:8].upper(),
    )
    permit.qr_payload = build_qr_payload(permit)
    permit.save(update_fields=["qr_payload"])
    from delayu.services.fuel_notify import notify_permit_approved_channels

    notify_permit_approved_channels(permit)
    if permit.assigned_azs:
        from delayu.services.fuel_capacity import refresh_azs_queue

        refresh_azs_queue(permit.assigned_azs)
    return permit


def application_form_initial(subsystem: Subsystem, citizen: FuelCitizen) -> dict:
    """Данные для автозаполнения формы из последней поданной заявки."""
    last = (
        FuelApplication.objects.filter(subsystem=subsystem, citizen=citizen)
        .exclude(status=FuelApplication.Status.DRAFT)
        .order_by("-created_at")
        .first()
    )
    if not last:
        return {}
    initial = {
        "category": last.category_id,
        "plate": last.plate,
        "vehicle_make": last.vehicle_make,
        "inn": last.inn,
        "org_name": last.org_name,
    }
    if last.assigned_azs_id:
        initial["preferred_azs"] = last.assigned_azs_id
    return initial


def fuel_azs_status_updated_at(subsystem: Subsystem):
    """Время последнего обновления статусов АЗС."""
    return subsystem.fuel_azs_stations.aggregate(ts=Max("updated_at"))["ts"]


def fuel_portal_checked_session_key(subsystem: Subsystem) -> str:
    return f"fuel_portal_checked_at_{subsystem.pk}"


def get_portal_checked_at(request, subsystem: Subsystem):
    """Когда пользователь последний раз нажимал «Обновить»."""
    raw = request.session.get(fuel_portal_checked_session_key(subsystem))
    if not raw:
        return None
    try:
        return timezone.datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def save_portal_checked_at(request, subsystem: Subsystem, moment=None):
    moment = moment or timezone.now()
    request.session[fuel_portal_checked_session_key(subsystem)] = moment.isoformat()
    request.session.modified = True
    return moment


def resolve_portal_checked_at(request, subsystem: Subsystem):
    """Время для подписи «Проверено» в UI."""
    user_checked = get_portal_checked_at(request, subsystem)
    if user_checked:
        return user_checked, True
    data_updated = fuel_azs_status_updated_at(subsystem)
    return data_updated, False


_FUEL_OPERATOR_PATH_SEGMENTS = frozenset({
    "dashboard",
    "leadership",
    "applications",
    "azs",
    "blacklist",
    "parity",
    "reports",
    "logs",
    "operator",
})


def _is_public_fuel_portal_path(path: str) -> bool:
    """Публичный портал жителя/АЗС: /fuel/<slug>/…, не кабинет оператора /fuel/dashboard/ и т.п."""
    parts = [p for p in (path or "").strip("/").split("/") if p]
    if len(parts) < 2 or parts[0] != "fuel":
        return False
    return parts[1] not in _FUEL_OPERATOR_PATH_SEGMENTS


def portal_page_load_touches_checked_at(request) -> bool:
    """Обычная загрузка HTML-страницы публичного портала — клиент получил свежие данные."""
    if (request.method or "").upper() != "GET":
        return False
    path = request.path or ""
    if not _is_public_fuel_portal_path(path):
        return False
    if "/api/" in path:
        return False
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return False
    return True


def _serialize_portal_azs(azs: FuelAzsStation) -> dict:
    from delayu.services.fuel_stock import serialize_azs_fuel_stock

    fuel = serialize_azs_fuel_stock(azs)
    return {
        "id": azs.pk,
        "name": azs.name,
        "address": azs.address,
        "district": azs.district,
        "status": azs.status,
        "fuel_grade": azs.fuel_grade,
        "queue_minutes": azs.queue_minutes,
        "stock_liters": azs.stock_liters,
        "fuel_stock_summary": fuel["summary"],
        "fuel_stock": fuel["items"],
        "is_accepting_permits": azs.is_accepting_permits,
        "latitude": float(azs.latitude) if azs.latitude is not None else None,
        "longitude": float(azs.longitude) if azs.longitude is not None else None,
    }


def fuel_portal_status_payload(
    subsystem: Subsystem, *, include_azs: bool = False, checked_at=None
) -> dict:
    """Статус портала; при include_azs — свежий снимок АЗС для обновления UI."""
    from delayu.services.fuel_analytics import azs_map_points

    updated = fuel_azs_status_updated_at(subsystem)
    user_refreshed = checked_at is not None
    display_checked = checked_at or updated or timezone.now()
    stale_minutes = 0
    stale = False
    if updated and not user_refreshed:
        stale_minutes = max(0, int((timezone.now() - updated).total_seconds() // 60))
        stale = stale_minutes > 30
    payload = {
        "updated_at": updated.isoformat() if updated else None,
        "updated_at_display": (
            timezone.localtime(updated).strftime("%d.%m.%Y %H:%M") if updated else None
        ),
        "checked_at": display_checked.isoformat(),
        "checked_at_display": timezone.localtime(display_checked).strftime("%d.%m.%Y %H:%M"),
        "stale": False if user_refreshed else stale,
        "stale_minutes": stale_minutes,
        "user_refreshed": user_refreshed,
        "server_time": timezone.now().isoformat(),
    }
    if include_azs:
        stations = list(subsystem.fuel_azs_stations.filter(is_archived=False).order_by("queue_minutes"))
        accepting = [s for s in stations if s.is_accepting_permits]
        payload["recommended_azs"] = [_serialize_portal_azs(s) for s in accepting[:3]]
        payload["azs_list"] = [_serialize_portal_azs(s) for s in stations]
        payload["map_points"] = azs_map_points(subsystem)
    return payload


def fuel_portal_azs_snapshot_json(subsystem: Subsystem) -> str:
    """JSON-снимок АЗС для офлайн-формы заявки."""
    import json

    stations = list(subsystem.fuel_azs_stations.filter(is_archived=False).order_by("queue_minutes"))
    return json.dumps(
        {
            "azs_list": [_serialize_portal_azs(s) for s in stations],
            "saved_at": timezone.now().isoformat(),
        },
        ensure_ascii=False,
    )


def fuel_apply_azs_url(request, azs_pk: int) -> str:
    """Ссылка на заявку с выбранной АЗС (через вход для гостя)."""
    from urllib.parse import quote

    from delayu.middleware.fuel_portal import require_fuel_subsystem

    root = getattr(request, "fuel_portal_root", "") or ""
    apply_url = f"{root}/apply/?azs={azs_pk}"
    subsystem = require_fuel_subsystem(request)
    if get_session_citizen(request, subsystem):
        return apply_url
    return f"{root}/login/?next={quote(apply_url, safe='')}"


def citizen_dashboard(subsystem: Subsystem, citizen: FuelCitizen) -> dict:
    active_permit = (
        FuelPermit.objects.filter(
            subsystem=subsystem,
            application__citizen=citizen,
            status=FuelPermit.Status.ACTIVE,
            valid_until__gte=timezone.now(),
            remaining_liters__gt=0,
        )
        .select_related("assigned_azs", "category", "application")
        .order_by("-created_at")
        .first()
    )
    active_permit_usage = permit_fuel_usage(active_permit) if active_permit else None
    applications = (
        FuelApplication.objects.filter(subsystem=subsystem, citizen=citizen)
        .select_related("category", "assigned_azs")
        .order_by("-created_at")[:20]
    )
    redeems = (
        FuelRedeem.objects.filter(
            subsystem=subsystem,
            permit__application__citizen=citizen,
        )
        .select_related("azs", "permit")
        .order_by("-created_at")[:20]
    )
    azs_list = FuelAzsStation.objects.filter(
        subsystem=subsystem, is_archived=False
    ).order_by("queue_minutes")
    recommended = recommend_azs(subsystem)
    return {
        "active_permit": active_permit,
        "active_permit_usage": active_permit_usage,
        "applications": applications,
        "redeems": redeems,
        "azs_list": azs_list,
        "recommended_azs": recommended,
        "azs_status_updated_at": fuel_azs_status_updated_at(subsystem),
        **application_queue_info(subsystem, citizen),
    }


def application_queue_info(subsystem: Subsystem, citizen: FuelCitizen) -> dict:
    """Позиция в очереди модерации (UI-3)."""
    pending = (
        FuelApplication.objects.filter(
            subsystem=subsystem,
            citizen=citizen,
            status=FuelApplication.Status.PENDING,
        )
        .order_by("created_at")
        .first()
    )
    if not pending:
        return {}
    ahead = FuelApplication.objects.filter(
        subsystem=subsystem,
        status=FuelApplication.Status.PENDING,
        created_at__lt=pending.created_at,
    ).count()
    total = FuelApplication.objects.filter(
        subsystem=subsystem,
        status=FuelApplication.Status.PENDING,
    ).count()
    return {
        "pending_application": pending,
        "queue_position": ahead + 1,
        "queue_total": total,
    }


REDEEM_MESSAGES = {
    "EXPIRED": "Срок действия пропуска истёк",
    "REVOKED": "Пропуск отозван",
    "LIMIT_EXCEEDED": "Суточный лимит по госномеру исчерпан",
    "BLACKLISTED": "Госномер в чёрном списке",
    "INVALID_SIGNATURE": "Недействительная подпись QR",
    "INVALID_JSON": "Некорректный QR-код",
    "NOT_FOUND": "Пропуск не найден",
    "INACTIVE": "Пропуск не активен",
    "NO_LITERS": "Нет доступных литров по пропуску",
    "AZS_CLOSED": "АЗС не принимает пропуска",
    "AMOUNT_EXCEEDED": "Запрошенный объём превышает остаток",
}


class RedeemError(Exception):
    def __init__(self, code: str):
        self.code = code
        self.message = REDEEM_MESSAGES.get(code, code)
        super().__init__(self.message)


def azs_session_key(subsystem_id: int) -> str:
    return f"fuel_azs_{subsystem_id}"


def get_session_azs(request, subsystem: Subsystem) -> FuelAzsStation | None:
    pk = request.session.get(azs_session_key(subsystem.pk))
    if not pk:
        return None
    return FuelAzsStation.objects.filter(pk=pk, subsystem=subsystem).first()


def login_azs(request, subsystem: Subsystem, login: str, pin: str) -> FuelAzsStation:
    station = FuelAzsStation.objects.filter(
        subsystem=subsystem,
        portal_login=login.strip(),
        portal_pin=pin.strip(),
    ).first()
    if not station:
        raise ValueError("Неверный логин или пароль")
    if station.is_archived:
        raise ValueError("АЗС снята с обслуживания")
    if station.portal_blocked:
        raise ValueError("Доступ к порталу АЗС заблокирован оператором")
    request.session[azs_session_key(subsystem.pk)] = station.pk
    request.session.modified = True
    return station


def logout_azs(request, subsystem: Subsystem) -> None:
    request.session.pop(azs_session_key(subsystem.pk), None)
    request.session.modified = True


def resolve_permit(
    subsystem: Subsystem,
    *,
    qr_payload: str = "",
    manual_code: str = "",
    permit_id: int | None = None,
) -> FuelPermit:
    permit = None
    if permit_id:
        permit = FuelPermit.objects.filter(pk=permit_id, subsystem=subsystem).first()
    elif manual_code:
        code = manual_code.strip().upper()
        permit = FuelPermit.objects.filter(
            subsystem=subsystem, manual_code__iexact=code
        ).first()
    elif qr_payload:
        data, err = verify_qr_payload(qr_payload.strip())
        if err:
            raise RedeemError(err)
        if int(data.get("sub", 0)) != subsystem.pk:
            raise RedeemError("NOT_FOUND")
        permit = FuelPermit.objects.filter(pk=data.get("pid"), subsystem=subsystem).first()
    if not permit:
        raise RedeemError("NOT_FOUND")
    return permit


def _validate_permit_for_redeem(permit: FuelPermit, azs: FuelAzsStation, liters: Decimal) -> None:
    if is_blacklisted(permit.subsystem, plate=permit.plate):
        raise RedeemError("BLACKLISTED")
    if permit.status != FuelPermit.Status.ACTIVE:
        raise RedeemError("REVOKED" if permit.status == FuelPermit.Status.REVOKED else "INACTIVE")
    if permit.valid_until < timezone.now():
        raise RedeemError("EXPIRED")
    if permit.remaining_liters <= 0:
        raise RedeemError("NO_LITERS")
    if not azs.is_accepting_permits or azs.status == FuelAzsStation.Status.EMPTY:
        raise RedeemError("AZS_CLOSED")
    daily = permit.category.daily_limit_liters
    redeemed = liters_redeemed_today(permit.subsystem, permit.plate)
    if redeemed + liters > daily:
        raise RedeemError("LIMIT_EXCEEDED")
    if liters > permit.remaining_liters:
        raise RedeemError("AMOUNT_EXCEEDED")


def preview_redeem(permit: FuelPermit, azs: FuelAzsStation, liters: Decimal) -> dict:
    _validate_permit_for_redeem(permit, azs, liters)
    daily = permit.category.daily_limit_liters
    redeemed = liters_redeemed_today(permit.subsystem, permit.plate)
    citizen_requested = getattr(permit.application, "requested_liters", None)
    return {
        "allowed": True,
        "plate": permit.plate,
        "permit_number": permit.number,
        "permit_id": permit.pk,
        "manual_code": permit.manual_code or "",
        "remaining_liters": int(permit.remaining_liters),
        "max_liters": int(permit.remaining_liters),
        "suggested_liters": float(liters),
        "requested_liters": float(liters),
        "citizen_requested_liters": citizen_requested,
        "category": permit.category.name,
        "daily_remaining": float(max(Decimal(0), daily - redeemed - liters)),
    }


def permit_fuel_usage(permit: FuelPermit) -> dict:
    """Сводка по отпускам по пропуску для портала жителя и оператора."""
    from django.db.models import Sum

    redeems = list(permit.redeems.select_related("azs").order_by("-created_at")[:10])
    agg = permit.redeems.aggregate(total=Sum("liters"))
    redeemed_total = agg["total"] or Decimal(0)
    return {
        "redeemed_total": redeemed_total,
        "remaining": int(permit.remaining_liters),
        "max_liters": int(permit.max_liters),
        "redeems": redeems,
    }


@transaction.atomic
def execute_redeem(
    permit: FuelPermit,
    azs: FuelAzsStation,
    liters: Decimal,
    *,
    operator_note: str = "",
) -> FuelRedeem:
    _validate_permit_for_redeem(permit, azs, liters)
    redeem = FuelRedeem.objects.create(
        subsystem=permit.subsystem,
        permit=permit,
        azs=azs,
        plate=permit.plate,
        liters=liters,
        operator_note=operator_note[:255],
    )
    permit.remaining_liters = max(0, int(Decimal(permit.remaining_liters) - liters))
    if permit.remaining_liters <= 0:
        permit.status = FuelPermit.Status.EXPIRED
    permit.qr_payload = build_qr_payload(permit)
    permit.save(update_fields=["remaining_liters", "status", "qr_payload"])
    from delayu.services.fuel_analytics import log_redeem_attempt

    log_redeem_attempt(
        permit.subsystem,
        azs=azs,
        plate=permit.plate,
        success=True,
        liters=liters,
    )
    from delayu.services.fuel_events import log_fuel_event

    log_fuel_event(
        permit.subsystem,
        "azs",
        "redeem.execute",
        f"Отпуск {liters} л · {permit.plate} · пропуск {permit.number}",
        azs=azs,
        object_type="FuelRedeem",
        object_id=redeem.pk,
        payload={"liters": float(liters), "permit_id": permit.pk},
    )
    from delayu.services.fuel_capacity import refresh_azs_queue

    refresh_azs_queue(azs)
    return redeem


@transaction.atomic
def reject_application(application: FuelApplication, reason: str = "") -> FuelApplication:
    application.status = FuelApplication.Status.REJECTED
    application.reject_reason = reason.strip()
    application.reviewed_at = timezone.now()
    application.save(update_fields=["status", "reject_reason", "reviewed_at"])
    return application


def update_azs_stock(
    azs: FuelAzsStation,
    stock_liters: int | None = None,
    queue_minutes: int | None = None,
    *,
    pump_count: int | None = None,
    avg_refuel_minutes: int | None = None,
    use_manual_queue: bool | None = None,
    stock_ai92_liters: int | None = None,
    stock_ai95_liters: int | None = None,
    stock_diesel_liters: int | None = None,
    stock_gas_liters: int | None = None,
    sells_ai92: bool | None = None,
    sells_ai95: bool | None = None,
    sells_diesel: bool | None = None,
    sells_gas: bool | None = None,
) -> FuelAzsStation:
    from delayu.services.fuel_stock import apply_azs_fuel_stock

    if any(
        v is not None
        for v in (
            stock_ai92_liters,
            stock_ai95_liters,
            stock_diesel_liters,
            stock_gas_liters,
            sells_ai92,
            sells_ai95,
            sells_diesel,
            sells_gas,
        )
    ):
        apply_azs_fuel_stock(
            azs,
            stock_ai92_liters=stock_ai92_liters,
            stock_ai95_liters=stock_ai95_liters,
            stock_diesel_liters=stock_diesel_liters,
            stock_gas_liters=stock_gas_liters,
            sells_ai92=sells_ai92,
            sells_ai95=sells_ai95,
            sells_diesel=sells_diesel,
            sells_gas=sells_gas,
        )
    elif stock_liters is not None:
        total = max(0, int(stock_liters))
        grade = (azs.fuel_grade or "АИ-95").upper()
        if "92" in grade:
            apply_azs_fuel_stock(azs, stock_ai92_liters=total, stock_ai95_liters=0)
        else:
            apply_azs_fuel_stock(azs, stock_ai95_liters=total, stock_ai92_liters=0)
    if pump_count is not None:
        azs.pump_count = max(1, pump_count)
    if avg_refuel_minutes is not None:
        azs.avg_refuel_minutes = max(1, avg_refuel_minutes)
    if use_manual_queue is not None:
        azs.use_manual_queue = use_manual_queue
    if queue_minutes is not None and (use_manual_queue is True or azs.use_manual_queue):
        azs.queue_minutes = max(0, min(queue_minutes, 999))
    azs.save()
    from delayu.services.fuel_capacity import refresh_azs_queue

    refresh_azs_queue(azs)
    return azs


def operator_dashboard(subsystem: Subsystem) -> dict:
    today = timezone.localdate()
    apps = FuelApplication.objects.filter(subsystem=subsystem, created_at__date=today)
    redeems = FuelRedeem.objects.filter(subsystem=subsystem, created_at__date=today)
    total_liters = redeems.aggregate(s=Sum("liters"))["s"] or 0
    return {
        "applications_today": apps.count(),
        "approved_today": apps.filter(status=FuelApplication.Status.APPROVED).count(),
        "pending": FuelApplication.objects.filter(
            subsystem=subsystem, status=FuelApplication.Status.PENDING
        ).count(),
        "redeems_today": redeems.count(),
        "liters_today": total_liters,
        "blacklist_count": FuelBlacklistEntry.objects.filter(
            subsystem=subsystem, is_active=True
        ).count(),
        "permits_active": FuelPermit.objects.filter(
            subsystem=subsystem,
            status=FuelPermit.Status.ACTIVE,
            valid_until__gte=timezone.now(),
        ).count(),
        "azs_overloaded": FuelAzsStation.objects.filter(
            subsystem=subsystem, status=FuelAzsStation.Status.BUSY, is_archived=False
        ).count(),
    }


def citizen_report_redeem_liters(
    redeem: FuelRedeem, citizen: FuelCitizen, liters: Decimal | None
) -> FuelRedeem:
    if redeem.permit.application.citizen_id != citizen.pk:
        raise ValueError("Нет доступа к этому отпуску")
    redeem.citizen_reported_liters = liters
    redeem.save(update_fields=["citizen_reported_liters"])
    return redeem


def azs_shift_stats(azs: FuelAzsStation) -> dict:
    today = timezone.localdate()
    redeems = FuelRedeem.objects.filter(azs=azs, created_at__date=today)
    total = redeems.aggregate(s=Sum("liters"))["s"] or 0
    return {
        "count": redeems.count(),
        "liters": total,
        "last": redeems.order_by("-created_at").first(),
        "recent": list(redeems.order_by("-created_at")[:8]),
    }
