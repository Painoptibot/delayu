"""Публичный портал гражданина — «Топливный пропуск»."""
from __future__ import annotations

from functools import wraps

from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.views import View
from django.views.decorators.csrf import csrf_protect
from django.utils.decorators import method_decorator

from delayu.forms_fuel import FuelApplicationForm, FuelCitizenLoginForm, FuelCitizenOtpForm
from delayu.middleware.fuel_portal import require_fuel_subsystem
from delayu.models_fuel import FuelApplication, FuelAzsStation, FuelCategory, FuelPermit
from delayu.services.fuel import (
    application_form_initial,
    citizen_dashboard,
    create_application,
    format_phone_display,
    fuel_azs_status_updated_at,
    fuel_portal_status_payload,
    get_portal_checked_at,
    get_session_citizen,
    login_citizen,
    logout_citizen,
    portal_page_load_touches_checked_at,
    resolve_portal_checked_at,
    save_portal_checked_at,
    fuel_portal_azs_snapshot_json,
)
from delayu.services.fuel_analytics import azs_map_points
from delayu.services.fuel_qr import qr_svg_for_permit
from delayu.services import dadata as dadata_service
from delayu.services.fuel_esia import (
    build_fuel_esia_url,
    fuel_esia_providers,
    resolve_fuel_esia_identity,
    validate_fuel_esia_callback,
)
from delayu.services.fuel_sms import link_citizen_esia, start_login_otp, verify_login_otp
from delayu.services.sso import SsoError


def _url_name(request, name: str, *args, **kwargs) -> str:
    sub = getattr(request, "fuel_subsystem", None)
    if sub and "subsystem_slug" not in kwargs:
        kwargs["subsystem_slug"] = sub.public_subdomain or sub.code
    try:
        return reverse(name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        kwargs.pop("subsystem_slug", None)
        path = reverse(name, args=args, kwargs=kwargs)
        root = getattr(request, "fuel_portal_root", "") or ""
        if root:
            return root.rstrip("/") + "/" + path.lstrip("/")
        return path


def fuel_portal_url(request, name: str, *args, **kwargs) -> str:
    return _url_name(request, name, *args, **kwargs)


class FuelPortalContextMixin:
    """Базовый контекст шаблонов портала."""

    def dispatch(self, request, *args, **kwargs):
        kwargs.pop("subsystem_slug", None)
        return super().dispatch(request, *args, **kwargs)

    def get_portal_context(self, request, extra=None):
        from django.conf import settings

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        ctx = {
            "subsystem": subsystem,
            "citizen": citizen,
            "portal_root": getattr(request, "fuel_portal_root", "") or "",
            "page_brand": f"Топливный пропуск · {subsystem.name}",
            "brand_color": subsystem.primary_color or "#2563eb",
        }
        from delayu.services.fuel import portal_public_banners, get_session_azs
        from delayu.services.fuel_notify import max_available

        root = getattr(request, "fuel_portal_root", "") or ""
        azs_station = get_session_azs(request, subsystem)
        ctx["azs_station"] = azs_station
        ctx["portal_banners"] = portal_public_banners(subsystem)
        ctx["max_available"] = max_available(subsystem)
        ctx["fuel_support_email"] = settings.FUEL_SUPPORT_EMAIL
        ctx["fuel_support_phone"] = settings.FUEL_SUPPORT_PHONE
        ctx["portal_legal_privacy_url"] = f"{root}/legal/privacy/"
        ctx["portal_legal_rules_url"] = f"{root}/legal/rules/"
        ctx["portal_support_url"] = f"{root}/support/"
        updated_at = fuel_azs_status_updated_at(subsystem)
        if portal_page_load_touches_checked_at(request):
            portal_checked_at = save_portal_checked_at(request, subsystem)
            portal_user_refreshed = True
        else:
            portal_checked_at, portal_user_refreshed = resolve_portal_checked_at(
                request, subsystem
            )
        ctx["azs_status_updated_at"] = updated_at
        ctx["portal_checked_at"] = portal_checked_at
        ctx["portal_user_refreshed"] = portal_user_refreshed
        ctx["fuel_status_api_url"] = f"{root}/api/status/"
        ctx["fuel_apply_sync_url"] = f"{root}/api/applications/sync/"
        ctx["fuel_sw_url"] = f"{root}/sw.js"
        if "/azs/" not in (request.path or ""):
            ctx["fuel_esia_providers"] = list(fuel_esia_providers(subsystem))
        if extra:
            ctx.update(extra)
        if "/azs/" in request.path:
            ctx["body_class"] = "fuel-body--azs"
        return ctx


def fuel_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        subsystem = require_fuel_subsystem(request)
        if not get_session_citizen(request, subsystem):
            login_url = fuel_portal_url(request, "fuel-citizen-login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        return view_func(request, *args, **kwargs)

    return wrapper


@method_decorator(csrf_protect, name="dispatch")
class FuelCitizenHomeView(FuelPortalContextMixin, View):
    template_name = "fuel/public/home.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        ctx = self.get_portal_context(request)
        if citizen:
            dash = citizen_dashboard(subsystem, citizen)
            ctx.update(dash)
            if dash.get("active_permit"):
                from django.utils.safestring import mark_safe

                from delayu.services.fuel_qr import qr_svg_for_permit

                ctx["active_permit_qr_svg"] = mark_safe(
                    qr_svg_for_permit(dash["active_permit"]).decode("utf-8")
                )
        else:
            azs_qs = subsystem.fuel_azs_stations.filter(is_archived=False).order_by("queue_minutes")
            ctx["recommended_azs"] = azs_qs[:3]
            ctx["azs_list"] = azs_qs
        return render(request, self.template_name, ctx)


@method_decorator(csrf_protect, name="dispatch")
class FuelCitizenLoginView(FuelPortalContextMixin, View):
    template_name = "fuel/public/login.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        if get_session_citizen(request, subsystem):
            return redirect(fuel_portal_url(request, "fuel-citizen-home"))
        ctx = self.get_portal_context(request, {"form": FuelCitizenLoginForm()})
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        form = FuelCitizenLoginForm(request.POST)
        if form.is_valid():
            demo_code = start_login_otp(
                request,
                subsystem,
                form.cleaned_data["phone"],
                form.cleaned_data["full_name"],
                channel=form.cleaned_data.get("notify_channel", "sms"),
                max_chat_id=form.cleaned_data.get("max_chat_id", ""),
            )
            request.session["fuel_login_phone_display"] = form.cleaned_data["phone"]
            channel = form.cleaned_data.get("notify_channel", "sms")
            labels = {"sms": "SMS", "max": "MAX", "both": "SMS и MAX"}
            request.session["fuel_login_channel_label"] = labels.get(channel, "SMS")
            if demo_code:
                from django.contrib import messages

                messages.info(
                    request,
                    f"Демо-режим SMS: код подтверждения {demo_code}",
                )
            return redirect(fuel_portal_url(request, "fuel-citizen-login-verify"))
        ctx = self.get_portal_context(request, {"form": form})
        return render(request, self.template_name, ctx, status=400)


@method_decorator(csrf_protect, name="dispatch")
class FuelCitizenLoginVerifyView(FuelPortalContextMixin, View):
    template_name = "fuel/public/login_verify.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        if get_session_citizen(request, subsystem):
            return redirect(fuel_portal_url(request, "fuel-citizen-home"))
        ctx = self.get_portal_context(
            request,
            {
                "form": FuelCitizenOtpForm(),
                "phone_display": request.session.get("fuel_login_phone_display", ""),
                "channel_label": request.session.get("fuel_login_channel_label", "SMS"),
            },
        )
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        form = FuelCitizenOtpForm(request.POST)
        if form.is_valid():
            verified = verify_login_otp(request, subsystem, form.cleaned_data["code"])
            if not verified:
                form.add_error("code", "Неверный или просроченный код")
            else:
                phone, full_name, max_chat_id, pd_consent = verified
                login_citizen(
                    request,
                    subsystem,
                    phone,
                    full_name,
                    max_chat_id=max_chat_id,
                    pd_consent=pd_consent,
                    auth_source="otp",
                )
                request.session.pop("fuel_login_phone_display", None)
                request.session.pop("fuel_login_channel_label", None)
                next_url = request.GET.get("next") or fuel_portal_url(
                    request, "fuel-citizen-home"
                )
                return redirect(next_url)
        ctx = self.get_portal_context(
            request,
            {
                "form": form,
                "phone_display": request.session.get("fuel_login_phone_display", ""),
                "channel_label": request.session.get("fuel_login_channel_label", "SMS"),
            },
        )
        return render(request, self.template_name, ctx, status=400)


class FuelCitizenLogoutView(FuelPortalContextMixin, View):
    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        logout_citizen(request, subsystem)
        return redirect(fuel_portal_url(request, "fuel-citizen-home"))

    def get(self, request):
        return self.post(request)


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_login_required, name="dispatch")
class FuelApplicationCreateView(FuelPortalContextMixin, View):
    template_name = "fuel/public/application_form.html"

    def _apply_context(self, request, subsystem, *, form, citizen=None):
        from delayu.services import dadata as dadata_service

        previous_initial = application_form_initial(subsystem, citizen) if citizen else {}
        preferred_azs_id = form.initial.get("preferred_azs") if getattr(form, "initial", None) else None
        if form.is_bound:
            preferred_azs_id = form.data.get("preferred_azs") or preferred_azs_id

        return self.get_portal_context(
            request,
            {
                "form": form,
                "azs_list": subsystem.fuel_azs_stations.filter(is_archived=False).order_by("queue_minutes"),
                "preferred_azs_id": preferred_azs_id,
                "from_previous_application": bool(previous_initial) and not form.is_bound,
                "dadata_configured": dadata_service.is_configured(),
                "taxi_category_pks": list(
                    FuelCategory.objects.filter(subsystem=subsystem, code="III").values_list(
                        "pk", flat=True
                    )
                ),
                "azs_snapshot_json": fuel_portal_azs_snapshot_json(subsystem),
            },
        )

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        initial = application_form_initial(subsystem, citizen)
        azs_param = request.GET.get("azs")
        if azs_param and str(azs_param).isdigit():
            azs = FuelAzsStation.objects.filter(
                subsystem=subsystem, pk=int(azs_param)
            ).first()
            if azs:
                initial["preferred_azs"] = azs.pk
        form = FuelApplicationForm(subsystem=subsystem, initial=initial)
        ctx = self._apply_context(request, subsystem, form=form, citizen=citizen)
        return render(request, self.template_name, ctx)

    def post(self, request):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        form = FuelApplicationForm(request.POST, subsystem=subsystem)
        if form.is_valid():
            preferred = None
            azs_id = form.cleaned_data.get("preferred_azs")
            if azs_id:
                preferred = FuelAzsStation.objects.filter(
                    pk=azs_id, subsystem=subsystem
                ).first()
            try:
                app = create_application(
                    subsystem=subsystem,
                    citizen=citizen,
                    category=form.cleaned_data["category"],
                    plate=form.cleaned_data["plate"],
                    vehicle_make=form.cleaned_data.get("vehicle_make", ""),
                    inn=form.cleaned_data.get("inn", ""),
                    org_name=form.cleaned_data.get("org_name", ""),
                    preferred_azs=preferred,
                )
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                return redirect(
                    fuel_portal_url(request, "fuel-application-detail", pk=app.pk)
                )
        ctx = self._apply_context(request, subsystem, form=form, citizen=citizen)
        return render(request, self.template_name, ctx, status=400)


@method_decorator(fuel_login_required, name="dispatch")
class FuelApplicationListView(FuelPortalContextMixin, View):
    template_name = "fuel/public/applications.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        apps = FuelApplication.objects.filter(
            subsystem=subsystem, citizen=citizen
        ).select_related("category", "assigned_azs")
        ctx = self.get_portal_context(request, {"applications": apps})
        return render(request, self.template_name, ctx)


@method_decorator(fuel_login_required, name="dispatch")
class FuelApplicationDetailView(FuelPortalContextMixin, View):
    template_name = "fuel/public/application_detail.html"

    def get(self, request, pk: int):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        app = get_object_or_404(
            FuelApplication,
            pk=pk,
            subsystem=subsystem,
            citizen=citizen,
        )
        permit = getattr(app, "permit", None)
        extra = {"application": app, "permit": permit}
        if permit:
            from delayu.services.fuel import permit_fuel_usage

            extra["permit_usage"] = permit_fuel_usage(permit)
        ctx = self.get_portal_context(request, extra)
        return render(request, self.template_name, ctx)


@method_decorator(fuel_login_required, name="dispatch")
class FuelPermitQrView(FuelPortalContextMixin, View):
    template_name = "fuel/public/permit_qr.html"

    def get(self, request, pk: int):
        from django.utils.safestring import mark_safe

        from delayu.services.fuel import permit_fuel_usage
        from delayu.services.fuel_qr import qr_svg_for_permit

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        permit = get_object_or_404(
            FuelPermit,
            pk=pk,
            subsystem=subsystem,
            application__citizen=citizen,
        )
        ctx = self.get_portal_context(
            request,
            {
                "permit": permit,
                "permit_usage": permit_fuel_usage(permit),
                "qr_svg": mark_safe(qr_svg_for_permit(permit).decode("utf-8")),
            },
        )
        return render(request, self.template_name, ctx)


@method_decorator(fuel_login_required, name="dispatch")
class FuelPermitQrSvgView(View):
    def dispatch(self, request, *args, **kwargs):
        kwargs.pop("subsystem_slug", None)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, pk: int):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        permit = get_object_or_404(
            FuelPermit,
            pk=pk,
            subsystem=subsystem,
            application__citizen=citizen,
        )
        return HttpResponse(qr_svg_for_permit(permit), content_type="image/svg+xml")


@method_decorator(fuel_login_required, name="dispatch")
class FuelMapView(FuelPortalContextMixin, View):
    template_name = "fuel/public/map.html"

    def get(self, request):
        import json

        from django.conf import settings

        subsystem = require_fuel_subsystem(request)
        azs_list = subsystem.fuel_azs_stations.filter(is_archived=False).order_by("queue_minutes")
        points = azs_map_points(subsystem)
        ctx = self.get_portal_context(
            request,
            {
                "azs_list": azs_list,
                "recommended_azs": azs_list.filter(is_accepting_permits=True)[:3],
                "map_points_json": json.dumps(points, ensure_ascii=False),
                "yandex_maps_api_key": getattr(settings, "YANDEX_MAPS_API_KEY", ""),
            },
        )
        return render(request, self.template_name, ctx)


@method_decorator(fuel_login_required, name="dispatch")
class FuelHistoryView(FuelPortalContextMixin, View):
    template_name = "fuel/public/history.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        dash = citizen_dashboard(subsystem, citizen)
        ctx = self.get_portal_context(
            request,
            {"redeems": dash["redeems"], "applications": dash["applications"]},
        )
        return render(request, self.template_name, ctx)


@method_decorator(csrf_protect, name="dispatch")
class FuelEsiaStartView(FuelPortalContextMixin, View):
    def get(self, request, pk: int):
        subsystem = require_fuel_subsystem(request)
        from delayu.models import SsoProvider

        provider = get_object_or_404(
            SsoProvider,
            pk=pk,
            subsystem=subsystem,
            is_active=True,
            provider_type=SsoProvider.ProviderType.ESIA,
        )
        try:
            url = build_fuel_esia_url(provider, request)
        except SsoError as exc:
            from django.contrib import messages

            messages.error(request, str(exc))
            return redirect(fuel_portal_url(request, "fuel-citizen-login"))
        return redirect(url)


class FuelEsiaCallbackView(FuelPortalContextMixin, View):
    def get(self, request):
        from django.contrib import messages

        subsystem = require_fuel_subsystem(request)
        try:
            provider, code = validate_fuel_esia_callback(request)
            redirect_uri = request.build_absolute_uri(
                (getattr(request, "fuel_portal_root", "") or "").rstrip("/")
                + "/auth/esia/callback/"
            )
            identity = resolve_fuel_esia_identity(provider, code, redirect_uri=redirect_uri)
            citizen = link_citizen_esia(
                subsystem,
                esia_oid=identity.get("esia_oid", ""),
                phone=identity.get("phone", ""),
                full_name=identity.get("full_name", ""),
            )
            login_citizen(
                request,
                subsystem,
                citizen.phone,
                citizen.full_name,
                auth_source="esia",
            )
        except SsoError as exc:
            messages.error(request, str(exc))
            return redirect(fuel_portal_url(request, "fuel-citizen-login"))
        request.session.pop("fuel_esia_state", None)
        request.session.pop("fuel_esia_provider_id", None)
        messages.success(request, "Вход через Госуслуги выполнен")
        return redirect(fuel_portal_url(request, "fuel-citizen-home"))


class FuelPortalStatusApiView(FuelPortalContextMixin, View):
    """Статус портала и время последнего обновления данных АЗС."""

    def dispatch(self, request, *args, **kwargs):
        kwargs.pop("subsystem_slug", None)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        include_azs = request.GET.get("refresh") == "1"
        if include_azs:
            checked_at = save_portal_checked_at(request, subsystem)
        else:
            checked_at = get_portal_checked_at(request, subsystem)
        response = JsonResponse(
            fuel_portal_status_payload(
                subsystem,
                include_azs=include_azs,
                checked_at=checked_at,
            )
        )
        response["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response


class FuelCitizenServiceWorkerView(View):
    """Service Worker портала жителя — кэш страниц и статики для офлайн."""

    def dispatch(self, request, *args, **kwargs):
        kwargs.pop("subsystem_slug", None)
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        from django.contrib.staticfiles.storage import staticfiles_storage
        from django.shortcuts import render

        subsystem = require_fuel_subsystem(request)
        root = getattr(request, "fuel_portal_root", "") or f"/fuel/{subsystem.public_subdomain or subsystem.code}"
        ctx = {
            "portal_root": root.rstrip("/"),
            "static_css": staticfiles_storage.url("css/fuel-citizen.css"),
            "static_js_status": staticfiles_storage.url("js/fuel-portal-status.js"),
            "static_js_offline": staticfiles_storage.url("js/fuel-citizen-offline.js"),
            "static_js_parity": staticfiles_storage.url("js/fuel-parity-banner.js"),
            "static_js_apply": staticfiles_storage.url("js/fuel-apply-form.js"),
        }
        response = render(request, "fuel/public/sw.js", ctx, content_type="application/javascript")
        response["Service-Worker-Allowed"] = root
        response["Cache-Control"] = "no-cache"
        return response


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(fuel_login_required, name="dispatch")
class FuelApplicationSyncApiView(View):
    """Синхронизация офлайн-очереди заявок жителя."""

    def dispatch(self, request, *args, **kwargs):
        kwargs.pop("subsystem_slug", None)
        return super().dispatch(request, *args, **kwargs)

    def post(self, request):
        import json

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        if not citizen:
            return JsonResponse({"ok": False, "error": "auth"}, status=401)
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

        synced_ids = request.session.setdefault("fuel_apply_synced_ids", [])
        results = []
        for item in body.get("items") or []:
            local_id = (item.get("local_id") or "").strip()
            payload = item.get("payload") or {}
            if local_id in synced_ids:
                results.append({"local_id": local_id, "ok": True, "duplicate": True})
                continue
            form = FuelApplicationForm(
                {
                    "category": payload.get("category"),
                    "plate": payload.get("plate", ""),
                    "vehicle_make": payload.get("vehicle_make", ""),
                    "inn": payload.get("inn", ""),
                    "org_name": payload.get("org_name", ""),
                    "preferred_azs": payload.get("preferred_azs") or None,
                    "agree_rules": "on" if payload.get("agree_rules") else "",
                },
                subsystem=subsystem,
            )
            if not form.is_valid():
                err = "; ".join(
                    f"{k}: {', '.join(v)}" for k, v in form.errors.items()
                )
                results.append({"local_id": local_id, "ok": False, "message": err})
                continue
            preferred = None
            azs_id = form.cleaned_data.get("preferred_azs")
            if azs_id:
                preferred = FuelAzsStation.objects.filter(
                    pk=azs_id, subsystem=subsystem
                ).first()
            try:
                app = create_application(
                    subsystem=subsystem,
                    citizen=citizen,
                    category=form.cleaned_data["category"],
                    plate=form.cleaned_data["plate"],
                    vehicle_make=form.cleaned_data.get("vehicle_make", ""),
                    inn=form.cleaned_data.get("inn", ""),
                    org_name=form.cleaned_data.get("org_name", ""),
                    preferred_azs=preferred,
                )
            except ValueError as exc:
                results.append({"local_id": local_id, "ok": False, "message": str(exc)})
            else:
                synced_ids.append(local_id)
                results.append(
                    {
                        "local_id": local_id,
                        "ok": True,
                        "application_id": app.pk,
                        "number": app.number,
                    }
                )
        request.session["fuel_apply_synced_ids"] = synced_ids[-200:]
        request.session.modified = True
        return JsonResponse({"ok": True, "results": results})


class FuelManifestView(FuelPortalContextMixin, View):
    """PWA-манифест портала жителя."""

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        root = getattr(request, "fuel_portal_root", "") or f"/fuel/{subsystem.public_subdomain or subsystem.code}"
        data = {
            "name": f"Топливный пропуск · {subsystem.name}",
            "short_name": "Топливо",
            "start_url": root + "/",
            "display": "standalone",
            "background_color": "#e8eef8",
            "theme_color": subsystem.primary_color or "#2563eb",
            "lang": "ru",
            "icons": [],
        }
        return JsonResponse(data)


@method_decorator(fuel_login_required, name="dispatch")
@method_decorator(csrf_protect, name="dispatch")
class FuelProfileView(FuelPortalContextMixin, View):
    """Профиль жителя — SMS-пропуск и уведомления (UI-3)."""
    template_name = "fuel/public/profile.html"

    def get(self, request):
        from django.conf import settings

        from delayu.services.fuel_notify import max_available
        from delayu.services.max_messenger import get_max_channel

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        sms_demo = settings.FUEL_SMS_DEMO_MODE
        max_channel = get_max_channel(subsystem) if max_available(subsystem) else None
        max_demo = bool(
            max_channel and (max_channel.webhook_url or "").startswith("demo:")
        )
        ctx = self.get_portal_context(
            request,
            {
                "phone_display": format_phone_display(citizen.phone),
                "sms_demo_mode": sms_demo,
                "max_demo_mode": max_demo,
                "notifications_demo_mode": sms_demo or max_demo,
            },
        )
        return render(request, self.template_name, ctx)

    def post(self, request):
        from django.contrib import messages

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        citizen.notify_sms = request.POST.get("notify_sms") == "on"
        citizen.notify_max = request.POST.get("notify_max") == "on"
        max_chat_id = (request.POST.get("max_chat_id") or "").strip()
        if max_chat_id:
            citizen.max_chat_id = max_chat_id
        citizen.save(update_fields=["notify_sms", "notify_max", "max_chat_id", "updated_at"])
        messages.success(request, "Настройки сохранены.")
        return redirect(fuel_portal_url(request, "fuel-profile"))


class FuelPartySuggestView(FuelPortalContextMixin, View):
    """Прокси DaData party для портала жителя (ИНН → название организации)."""

    def post(self, request):
        import json

        require_fuel_subsystem(request)
        try:
            body = json.loads(request.body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "invalid_json"}, status=400)
        query = (body.get("query") or "").strip()
        if len(query) < 3:
            return JsonResponse(
                {"suggestions": [], "configured": dadata_service.is_configured()}
            )
        result = dadata_service.suggest(
            "party", query, count=8, extra={"status": ["ACTIVE"]}
        )
        return JsonResponse(result)


class FuelVehicleSuggestView(FuelPortalContextMixin, View):
    """Подсказки марки/модели ТС (RU/EN)."""

    def get(self, request):
        from delayu.services.fuel_vehicles import suggest_vehicles

        require_fuel_subsystem(request)
        query = (request.GET.get("q") or "").strip()
        suggestions = suggest_vehicles(query)
        return JsonResponse({"suggestions": suggestions})


class FuelLegalPrivacyView(FuelPortalContextMixin, View):
    template_name = "fuel/public/legal_privacy.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        return render(request, self.template_name, self.get_portal_context(request))


class FuelLegalRulesView(FuelPortalContextMixin, View):
    template_name = "fuel/public/legal_rules.html"

    def get(self, request):
        subsystem = require_fuel_subsystem(request)
        return render(request, self.template_name, self.get_portal_context(request))


@method_decorator(csrf_protect, name="dispatch")
class FuelSupportView(FuelPortalContextMixin, View):
    template_name = "fuel/public/support.html"

    def get(self, request):
        from delayu.forms_fuel_support import FuelSupportForm

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        initial = {}
        if citizen:
            initial = {
                "name": citizen.full_name,
                "contact": format_phone_display(citizen.phone),
            }
        ctx = self.get_portal_context(request, {"form": FuelSupportForm(initial=initial)})
        if citizen:
            from delayu.models_fuel import FuelSupportTicket

            ctx["my_tickets"] = FuelSupportTicket.objects.filter(
                subsystem=subsystem, citizen=citizen
            ).order_by("-created_at")[:20]
        return render(request, self.template_name, ctx)

    def post(self, request):
        from django.contrib import messages

        from delayu.forms_fuel_support import FuelSupportForm
        from delayu.services.fuel_notify import log_support_question

        subsystem = require_fuel_subsystem(request)
        citizen = get_session_citizen(request, subsystem)
        form = FuelSupportForm(request.POST)
        if form.is_valid():
            log_support_question(
                subsystem,
                citizen=citizen,
                name=form.cleaned_data["name"],
                contact=form.cleaned_data["contact"],
                question=form.cleaned_data["question"],
            )
            messages.success(request, "Вопрос отправлен. Мы ответим по указанному контакту.")
            return redirect(fuel_portal_url(request, "fuel-support"))
        ctx = self.get_portal_context(request, {"form": form})
        return render(request, self.template_name, ctx, status=400)
