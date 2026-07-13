"""Портал оператора АЗС — «Топливный пропуск»."""
from __future__ import annotations

import json
from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from delayu.forms_fuel import (
    FuelAzsLoginForm,
    FuelAzsManualCodeForm,
    FuelAzsRedeemForm,
    FuelAzsStockForm,
)
from delayu.middleware.fuel_portal import require_fuel_subsystem
from delayu.models_fuel import FuelPermit
from delayu.services.fuel import (
    RedeemError,
    azs_shift_stats,
    execute_redeem,
    get_session_azs,
    login_azs,
    logout_azs,
    preview_redeem,
    resolve_permit,
    update_azs_stock,
)
from delayu.views_fuel_public import FuelPortalContextMixin, fuel_portal_url


def fuel_azs_required(view_func):
    def wrapper(request, *args, **kwargs):
        subsystem = require_fuel_subsystem(request)
        if not get_session_azs(request, subsystem):
            return redirect(fuel_portal_url(request, "fuel-azs-login"))
        return view_func(request, *args, **kwargs)

    return wrapper


@method_decorator(csrf_protect, name="dispatch")
class FuelAzsLoginView(FuelPortalContextMixin, View):
    template_name = "fuel/azs/login.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        if get_session_azs(request, subsystem):
            return redirect(fuel_portal_url(request, "fuel-azs-scan"))
        ctx = self.get_portal_context(request, {"form": FuelAzsLoginForm()})
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        form = FuelAzsLoginForm(request.POST)
        if form.is_valid():
            try:
                login_azs(request, subsystem, form.cleaned_data["login"], form.cleaned_data["pin"])
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                station = get_session_azs(request, subsystem)
                from delayu.services.fuel_events import log_fuel_event

                log_fuel_event(
                    subsystem,
                    "azs",
                    "azs.login",
                    f"Вход в портал АЗС «{station.name}»",
                    azs=station,
                    request=request,
                )
                return redirect(fuel_portal_url(request, "fuel-azs-scan"))
        ctx = self.get_portal_context(request, {"form": form})
        return render(request, self.template_name, ctx, status=400)


@method_decorator(csrf_protect, name="dispatch")
class FuelAzsLogoutView(FuelPortalContextMixin, View):
    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        logout_azs(request, subsystem)
        from delayu.services.fuel_events import log_fuel_event

        log_fuel_event(
            subsystem,
            "azs",
            "azs.logout",
            f"Выход из портала АЗС{f' «{station.name}»' if station else ''}",
            azs=station,
            request=request,
        )
        return redirect(fuel_portal_url(request, "fuel-azs-login"))

    def get(self, request):
        return self.post(request)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_azs_required, name="dispatch")
class FuelAzsScanView(FuelPortalContextMixin, View):
    template_name = "fuel/azs/scan.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        preview = request.session.pop("fuel_redeem_preview", None)
        success = request.session.pop("fuel_redeem_success", None)
        ctx = self.get_portal_context(
            request,
            {
                "station": station,
                "manual_form": FuelAzsManualCodeForm(),
                "preview": preview,
                "success": success,
                "stats": azs_shift_stats(station),
            },
        )
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        qr_payload = request.POST.get("qr_payload", "")
        manual_form = FuelAzsManualCodeForm(request.POST)
        try:
            if qr_payload:
                permit = resolve_permit(subsystem, qr_payload=qr_payload)
            elif manual_form.is_valid():
                permit = resolve_permit(
                    subsystem, manual_code=manual_form.cleaned_data["manual_code"]
                )
            else:
                ctx = self.get_portal_context(
                    request,
                    {
                        "station": station,
                        "manual_form": manual_form,
                        "error": "Укажите QR или код",
                        "stats": azs_shift_stats(station),
                    },
                )
                return render(request, self.template_name, ctx, status=400)
            default_liters = min(Decimal(permit.remaining_liters), Decimal(permit.category.daily_limit_liters))
            preview = preview_redeem(permit, station, default_liters)
            preview["permit_id"] = permit.pk
            preview["default_liters"] = float(default_liters)
            if qr_payload:
                preview["qr_payload"] = qr_payload
            request.session["fuel_redeem_preview"] = preview
        except RedeemError as exc:
            from delayu.services.fuel_analytics import log_redeem_attempt

            log_redeem_attempt(
                subsystem,
                azs=station,
                plate=request.POST.get("plate", ""),
                success=False,
                error_code=exc.code,
            )
            ctx = self.get_portal_context(
                request,
                {
                    "station": station,
                    "manual_form": manual_form if not qr_payload else FuelAzsManualCodeForm(),
                    "denied": {"code": exc.code, "message": exc.message},
                    "stats": azs_shift_stats(station),
                },
            )
            return render(request, self.template_name, ctx)
        return redirect(fuel_portal_url(request, "fuel-azs-confirm"))


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_azs_required, name="dispatch")
class FuelAzsConfirmView(FuelPortalContextMixin, View):
    template_name = "fuel/azs/confirm.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        preview = request.session.get("fuel_redeem_preview")
        if not preview:
            return redirect(fuel_portal_url(request, "fuel-azs-scan"))
        form = FuelAzsRedeemForm(initial={"liters": preview.get("default_liters")})
        ctx = self.get_portal_context(request, {"station": station, "preview": preview, "form": form})
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        preview = request.session.get("fuel_redeem_preview")
        if not preview:
            return redirect(fuel_portal_url(request, "fuel-azs-scan"))
        form = FuelAzsRedeemForm(request.POST)
        if form.is_valid():
            permit = FuelPermit.objects.filter(pk=preview["permit_id"], subsystem=subsystem).first()
            if not permit:
                request.session.pop("fuel_redeem_preview", None)
                return redirect(fuel_portal_url(request, "fuel-azs-scan"))
            try:
                execute_redeem(
                    permit,
                    station,
                    form.cleaned_data["liters"],
                    operator_note=form.cleaned_data.get("operator_note", ""),
                )
            except RedeemError as exc:
                form.add_error(None, exc.message)
            else:
                request.session.pop("fuel_redeem_preview", None)
                request.session["fuel_redeem_success"] = {
                    "plate": permit.plate,
                    "liters": float(form.cleaned_data["liters"]),
                }
                return redirect(fuel_portal_url(request, "fuel-azs-scan"))
        ctx = self.get_portal_context(
            request, {"station": station, "preview": preview, "form": form}
        )
        return render(request, self.template_name, ctx, status=400)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_azs_required, name="dispatch")
class FuelAzsStockView(FuelPortalContextMixin, View):
    template_name = "fuel/azs/stock.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        form = FuelAzsStockForm(
            initial={
                "stock_liters": station.stock_liters,
                "queue_minutes": station.queue_minutes,
                "pump_count": station.pump_count,
                "avg_refuel_minutes": station.avg_refuel_minutes,
                "use_manual_queue": station.use_manual_queue,
            }
        )
        from delayu.services.fuel_capacity import azs_capacity_snapshot, get_portal_settings

        settings = get_portal_settings(subsystem)
        cap = azs_capacity_snapshot(station, settings)
        ctx = self.get_portal_context(
            request,
            {"station": station, "form": form, "capacity": cap, "portal_settings": settings},
        )
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        form = FuelAzsStockForm(request.POST)
        if form.is_valid():
            queue = form.cleaned_data.get("queue_minutes")
            if not form.cleaned_data.get("use_manual_queue"):
                queue = None
            update_azs_stock(
                station,
                form.cleaned_data["stock_liters"],
                queue,
                pump_count=form.cleaned_data["pump_count"],
                avg_refuel_minutes=form.cleaned_data["avg_refuel_minutes"],
                use_manual_queue=form.cleaned_data.get("use_manual_queue", False),
            )
            from delayu.services.fuel_events import log_fuel_event

            log_fuel_event(
                subsystem,
                "azs",
                "azs.stock_update",
                f"Обновлён остаток: {form.cleaned_data['stock_liters']} л, колонок {form.cleaned_data['pump_count']}",
                azs=station,
                object_type="FuelAzsStation",
                object_id=station.pk,
                request=request,
            )
            station.refresh_from_db()
            from delayu.services.fuel_capacity import azs_capacity_snapshot, get_portal_settings

            settings = get_portal_settings(subsystem)
            cap = azs_capacity_snapshot(station, settings)
            ctx = self.get_portal_context(
                request,
                {
                    "station": station,
                    "form": form,
                    "saved": True,
                    "capacity": cap,
                    "portal_settings": settings,
                },
            )
            return render(request, self.template_name, ctx)
        ctx = self.get_portal_context(request, {"station": station, "form": form})
        return render(request, self.template_name, ctx, status=400)


@method_decorator(fuel_azs_required, name="dispatch")
class FuelAzsVerifyApiView(FuelPortalContextMixin, View):
    """JSON-проверка QR для сканера (камера)."""

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        if not station:
            return JsonResponse({"error": "unauthorized"}, status=401)
        payload = request.POST.get("qr_payload", "")
        try:
            permit = resolve_permit(subsystem, qr_payload=payload)
            liters = min(Decimal(permit.remaining_liters), Decimal("30"))
            data = preview_redeem(permit, station, liters)
            data["permit_id"] = permit.pk
            request.session["fuel_redeem_preview"] = {**data, "default_liters": float(liters)}
            return JsonResponse(data)
        except RedeemError as exc:
            return JsonResponse({"allowed": False, "code": exc.code, "message": exc.message}, status=400)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_azs_required, name="dispatch")
class FuelAzsSyncApiView(FuelPortalContextMixin, View):
    """Синхронизация офлайн-очереди отпусков (UI-3)."""

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        station = get_session_azs(request, subsystem)
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        results = []
        for item in body.get("items") or []:
            local_id = item.get("local_id", "")
            try:
                liters = Decimal(str(item.get("liters", "0")))
                permit_id = item.get("permit_id")
                qr_payload = item.get("qr_payload", "")
                if permit_id:
                    permit = FuelPermit.objects.filter(pk=permit_id, subsystem=subsystem).first()
                    if not permit:
                        raise RedeemError("NOT_FOUND")
                elif qr_payload:
                    permit = resolve_permit(subsystem, qr_payload=qr_payload)
                else:
                    raise RedeemError("NOT_FOUND")
                execute_redeem(
                    permit,
                    station,
                    liters,
                    operator_note=item.get("operator_note", ""),
                )
                results.append({"local_id": local_id, "ok": True})
            except RedeemError as exc:
                results.append(
                    {
                        "local_id": local_id,
                        "ok": False,
                        "code": exc.code,
                        "message": exc.message,
                    }
                )
        return JsonResponse({"ok": True, "results": results})
