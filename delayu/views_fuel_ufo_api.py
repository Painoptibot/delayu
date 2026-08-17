# -*- coding: utf-8 -*-
"""Публичное API мобильного приложения «Топливный пропуск» (ЮФО)."""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from delayu.models_fuel_ufo import (
    FuelUfoAvailability,
    FuelUfoAzsPoint,
    FuelUfoRegion,
    FuelUfoRegionBanner,
    point_in_ufo,
)
from delayu.services import fuel_ufo as svc


def _json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _opt_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FuelUfoAzsListApi(View):
    """GET /fuel/api/ufo/azs/"""

    def get(self, request):
        qs = FuelUfoAzsPoint.objects.filter(is_active=True).select_related("snapshot")
        region = (request.GET.get("region") or "").strip()
        if region:
            if region not in FuelUfoRegion.values:
                return JsonResponse({"error": "unknown_region"}, status=400)
            qs = qs.filter(region=region)
        city = (request.GET.get("city") or "").strip()
        if city:
            qs = qs.filter(city__icontains=city)
        network = (request.GET.get("network") or "").strip()
        if network:
            qs = qs.filter(network=network)
        q = (request.GET.get("q") or "").strip()
        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(name__icontains=q) | Q(address__icontains=q) | Q(city__icontains=q) | Q(network__icontains=q)
            )
        try:
            if request.GET.get("min_lat"):
                qs = qs.filter(latitude__gte=float(request.GET["min_lat"]))
            if request.GET.get("max_lat"):
                qs = qs.filter(latitude__lte=float(request.GET["max_lat"]))
            if request.GET.get("min_lon"):
                qs = qs.filter(longitude__gte=float(request.GET["min_lon"]))
            if request.GET.get("max_lon"):
                qs = qs.filter(longitude__lte=float(request.GET["max_lon"]))
        except ValueError:
            return JsonResponse({"error": "bad_bbox"}, status=400)

        grade = (request.GET.get("grade") or "").strip().lower()
        only_available = (request.GET.get("available") or "").strip() in ("1", "true", "yes")

        items = [svc.serialize_azs(a) for a in qs[:2000]]
        if grade in ("ai92", "ai95", "diesel"):
            if only_available:
                items = [
                    i
                    for i in items
                    if i["status"].get(grade)
                    in (FuelUfoAvailability.OK, FuelUfoAvailability.LOW)
                ]
            # полезный порядок: есть → мало → неизвестно → нет; свежее выше
            rank = {"ok": 0, "low": 1, "unknown": 2, "empty": 3}

            def _key(i):
                st = i["status"].get(grade) or "unknown"
                fresh = i.get("freshness_minutes")
                fresh_key = fresh if fresh is not None else 10**9
                return (rank.get(st, 9), fresh_key)

            items.sort(key=_key)
        return JsonResponse({"scope": "ufo", "count": len(items), "results": items})


class FuelUfoAzsDetailApi(View):
    def get(self, request, pk: int):
        try:
            azs = FuelUfoAzsPoint.objects.select_related("snapshot").get(pk=pk, is_active=True)
        except FuelUfoAzsPoint.DoesNotExist:
            return JsonResponse({"error": "not_found"}, status=404)
        return JsonResponse(svc.serialize_azs(azs))


@method_decorator(csrf_exempt, name="dispatch")
class FuelUfoReportApi(View):
    """POST /fuel/api/ufo/reports/"""

    def post(self, request):
        from delayu.services import fuel_ufo_auth as auth

        user = auth.current_ufo_user(request)
        if not user:
            return JsonResponse(
                {
                    "error": "auth_required",
                    "detail": "Войдите, чтобы отметить наличие. Один раз в сутки — по своей АЗС.",
                },
                status=401,
            )
        data = _json_body(request)
        try:
            azs_id = int(data.get("azs_id"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "azs_id_required"}, status=400)
        device_id = (data.get("device_id") or request.META.get("HTTP_X_DEVICE_ID") or "").strip()
        availability = data.get("availability") or FuelUfoAvailability.UNKNOWN
        if availability not in FuelUfoAvailability.values:
            return JsonResponse({"error": "bad_availability"}, status=400)
        try:
            azs = FuelUfoAzsPoint.objects.get(pk=azs_id, is_active=True)
        except FuelUfoAzsPoint.DoesNotExist:
            return JsonResponse({"error": "not_found"}, status=404)
        try:
            report = svc.add_user_report(
                azs=azs,
                device_id=device_id,
                phone=user.get("phone") or "",
                availability=availability,
                fuel_grade=(data.get("fuel_grade") or "ai95")[:16],
                queue_minutes=_opt_int(data.get("queue_minutes")),
                limit_liters=_opt_int(data.get("limit_liters")),
                cans_allowed=data.get("cans_allowed"),
                comment=data.get("comment") or "",
                lat=_opt_float(data.get("lat")),
                lon=_opt_float(data.get("lon")),
            )
        except PermissionError as e:
            quota = svc.user_report_quota(phone=user.get("phone") or "")
            return JsonResponse(
                {"error": quota.get("reason") or "rate_limited", "detail": str(e), "report_quota": quota},
                status=429,
            )
        quota = svc.user_report_quota(phone=user.get("phone") or "")
        return JsonResponse(
            {"ok": True, "report_id": report.id, "azs": svc.serialize_azs(azs), "report_quota": quota},
            status=201,
        )

    def get(self, request):
        from delayu.models_fuel_ufo import FuelUfoUserReport
        from delayu.services import fuel_ufo_auth as auth

        user = auth.current_ufo_user(request)
        device_id = (request.GET.get("device_id") or request.META.get("HTTP_X_DEVICE_ID") or "").strip()
        qs = FuelUfoUserReport.objects.select_related("azs").order_by("-created_at")
        if user and user.get("phone"):
            qs = qs.filter(phone=user["phone"])
        elif len(device_id) >= 8:
            qs = qs.filter(device_id=device_id)
        else:
            return JsonResponse({"error": "auth_required"}, status=401)
        rows = list(qs[:50])
        phone = (user or {}).get("phone") or ""
        return JsonResponse(
            {
                "ok": True,
                "count": len(rows),
                "report_quota": svc.user_report_quota(phone=phone),
                "results": [
                    {
                        "id": r.id,
                        "azs_id": r.azs_id,
                        "azs_name": r.azs.name,
                        "city": r.azs.city,
                        "availability": r.availability,
                        "fuel_grade": r.fuel_grade,
                        "queue_minutes": r.queue_minutes,
                        "comment": r.comment,
                        "created_at": r.created_at.isoformat(),
                    }
                    for r in rows
                ],
            }
        )


class FuelUfoMetaApi(View):
    """GET /fuel/api/ufo/meta/ — регионы, баннеры, политика freshness."""

    def get(self, request):
        banners = [
            {
                "region": b.region,
                "title": b.title,
                "body": b.body,
                "updated_at": b.updated_at.isoformat(),
            }
            for b in FuelUfoRegionBanner.objects.filter(is_active=True)
        ]
        return JsonResponse(
            {
                "scope": "ufo",
                "regions": [{"code": c, "name": n} for c, n in FuelUfoRegion.choices],
                "banners": banners,
                "availability": [{"code": c, "name": n} for c, n in FuelUfoAvailability.choices],
                "networks": svc.list_networks(),
                "bbox": {"min_lat": 43.0, "min_lon": 32.0, "max_lat": 51.5, "max_lon": 49.5},
                "product": {
                    "title": "Топливный пропуск",
                    "tagline": "Где заправиться сейчас в ЮФО",
                    "grades": [
                        {"code": "ai95", "name": "АИ-95"},
                        {"code": "ai92", "name": "АИ-92"},
                        {"code": "diesel", "name": "ДТ"},
                    ],
                },
            }
        )


class FuelUfoGeoCheckApi(View):
    def get(self, request):
        try:
            lat = float(request.GET.get("lat"))
            lon = float(request.GET.get("lon"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "lat_lon_required"}, status=400)
        return JsonResponse({"in_ufo": point_in_ufo(lat, lon), "lat": lat, "lon": lon})


class FuelUfoRouteApi(View):
    """GET /fuel/api/ufo/route/ — маршрут до АЗС внутри приложения."""

    def get(self, request):
        try:
            from_lat = float(request.GET.get("from_lat"))
            from_lon = float(request.GET.get("from_lon"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "from_required"}, status=400)
        azs = None
        try:
            azs_id = request.GET.get("azs_id")
            if azs_id:
                azs = FuelUfoAzsPoint.objects.select_related("snapshot").get(
                    pk=int(azs_id), is_active=True
                )
                to_lat = float(azs.latitude)
                to_lon = float(azs.longitude)
            else:
                to_lat = float(request.GET.get("to_lat"))
                to_lon = float(request.GET.get("to_lon"))
        except (TypeError, ValueError, FuelUfoAzsPoint.DoesNotExist):
            return JsonResponse({"error": "destination_required"}, status=400)
        try:
            route = svc.build_drive_route(
                from_lat=from_lat, from_lon=from_lon, to_lat=to_lat, to_lon=to_lon
            )
        except ValueError as exc:
            return JsonResponse({"error": "out_of_scope", "detail": str(exc)}, status=400)
        payload = {"ok": True, **route, "to": {"lat": to_lat, "lon": to_lon}}
        if azs:
            payload["azs"] = svc.serialize_azs(azs)
        return JsonResponse(payload)


class FuelUfoStatusApi(View):
    """GET /fuel/api/ufo/status/ — пульс сервиса для офлайн-индикатора."""

    def get(self, request):
        from django.utils import timezone

        count = FuelUfoAzsPoint.objects.filter(is_active=True).count()
        return JsonResponse(
            {
                "ok": True,
                "online": True,
                "scope": "ufo",
                "azs_count": count,
                "checked_at": timezone.now().isoformat(),
                "title": "Сервис: онлайн",
                "product": "Топливный пропуск · ЮФО",
            }
        )


@method_decorator(csrf_exempt, name="dispatch")
class FuelUfoAuthStartApi(View):
    def post(self, request):
        from delayu.services import fuel_ufo_auth as auth

        data = _json_body(request)
        agree = data.get("agree_pd") in (True, "1", "true", "on", "yes")
        if not agree:
            return JsonResponse({"error": "agree_pd_required", "detail": "Нужно согласие на обработку данных"}, status=400)
        try:
            payload = auth.start_ufo_otp(data.get("phone") or "", data.get("full_name") or "")
        except ValueError as exc:
            return JsonResponse({"error": "invalid", "detail": str(exc)}, status=400)
        return JsonResponse(payload)


@method_decorator(csrf_exempt, name="dispatch")
class FuelUfoAuthVerifyApi(View):
    def post(self, request):
        from delayu.services import fuel_ufo_auth as auth

        data = _json_body(request)
        user = auth.verify_ufo_otp(request, data.get("phone") or "", data.get("code") or "")
        if not user:
            return JsonResponse({"error": "bad_code", "detail": "Неверный или просроченный код"}, status=400)
        return JsonResponse(
            {
                "ok": True,
                "user": user,
                "report_quota": svc.user_report_quota(phone=user.get("phone") or ""),
            }
        )


class FuelUfoAuthMeApi(View):
    def get(self, request):
        from delayu.services import fuel_ufo_auth as auth

        user = auth.current_ufo_user(request)
        if not user:
            return JsonResponse({"ok": False, "user": None, "report_quota": svc.user_report_quota(phone="")})
        return JsonResponse(
            {"ok": True, "user": user, "report_quota": svc.user_report_quota(phone=user.get("phone") or "")}
        )


@method_decorator(csrf_exempt, name="dispatch")
class FuelUfoAuthLogoutApi(View):
    def post(self, request):
        from delayu.services import fuel_ufo_auth as auth

        auth.logout_ufo(request)
        return JsonResponse({"ok": True})
