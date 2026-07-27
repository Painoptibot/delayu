"""Mock / demo SMEV for invest contour (enterprise demo layer)."""
from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from io import BytesIO

from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from delayu.models_invest import (
    InvestPackageItem,
    InvestSite,
    InvestSmevInfoType,
    InvestSmevRequest,
    InvestStopFactor,
)
from delayu.services.invest_flags import ensure_automation_config
from delayu.services.invest_package import ensure_package

CRITICAL_ENCUMBRANCE_KEYWORDS = (
    "критич",
    "запрет",
    "ограничение",
    "санитарно-защит",
    "оопт",
)

APPLY_FIELDS = (
    "address",
    "land_category",
    "vri",
    "right_type",
    "encumbrances",
    "zone_info",
    "area_ha",
    "latitude",
    "longitude",
)


class InvestSmevError(Exception):
    pass


def _diff_value(value):
    if value is None:
        return None
    return str(value)


def _new_ids() -> tuple[str, str]:
    correlation = uuid.uuid4().hex
    message = uuid.uuid4().hex
    return correlation, message


def _mock_egrn_payload(cadastral_number: str) -> dict:
    digest = hashlib.sha1(cadastral_number.encode("utf-8")).hexdigest()
    area = Decimal((int(digest[:4], 16) % 9000) + 1000) / Decimal("100")
    lat = Decimal("45.") + Decimal(int(digest[4:8], 16) % 9000) / Decimal("100000")
    lon = Decimal("38.") + Decimal(int(digest[8:12], 16) % 9000) / Decimal("100000")
    categories = (
        "земли промышленности",
        "земли населённых пунктов",
        "земли сельхозназначения",
    )
    rights = ("собственность РФ", "собственность субъекта РФ", "аренда", "постоянное пользование")
    vris = (
        "производство",
        "складские объекты",
        "туристско-рекреационная деятельность",
        "для размещения промышленных объектов",
    )
    return {
        "cadastral_number": cadastral_number,
        "address": f"Краснодарский край, кадастр {cadastral_number}",
        "area_ha": str(area),
        "land_category": categories[int(digest[12], 16) % len(categories)],
        "vri": vris[int(digest[13], 16) % len(vris)],
        "right_type": rights[int(digest[14], 16) % len(rights)],
        "encumbrances": "Охранная зона сетей — уточнить по ответу ОИВ" if int(digest[15], 16) % 2 else "",
        "zone_info": "Черновик пересечений РГИС: без критичных ООПТ (mock)",
        "latitude": str(lat),
        "longitude": str(lon),
        "source": "mock-smev-egrn",
        "received_at": timezone.now().isoformat(),
    }


def _mock_stub_payload(service: str, cadastral_number: str) -> dict:
    return {
        "note": f"Mock-ответ сервиса {service} для {cadastral_number}",
        "cadastral_number": cadastral_number,
        "source": f"mock-smev-{service}",
        "received_at": timezone.now().isoformat(),
    }


def ensure_default_info_types() -> None:
    defaults = [
        (
            "egrn-basic",
            {
                "name": "ЕГРН: сведения об участке",
                "service": InvestSmevRequest.Service.EGRN,
                "contract_version": "demo-1",
                "schema_json": {"required": ["cadastral_number", "address", "area_ha", "land_category"]},
                "is_active": True,
            },
        ),
        (
            "isogd-zone",
            {
                "name": "ИСОГД: градостроительные зоны",
                "service": InvestSmevRequest.Service.ISOGD,
                "contract_version": "demo-1",
                "schema_json": {"required": ["note"]},
                "is_active": True,
            },
        ),
        (
            "rgis-intersections",
            {
                "name": "РГИС: пересечения и ограничения",
                "service": InvestSmevRequest.Service.RGIS,
                "contract_version": "demo-1",
                "schema_json": {"required": ["note"]},
                "is_active": True,
            },
        ),
    ]
    for code, values in defaults:
        InvestSmevInfoType.objects.update_or_create(code=code, defaults=values)


def validate_smev_response(info_type: InvestSmevInfoType, payload: dict, request: InvestSmevRequest | None = None) -> list[str]:
    required = list((info_type.schema_json or {}).get("required") or [])
    missing = [key for key in required if not (payload or {}).get(key)]
    if request is not None and missing:
        request.status = InvestSmevRequest.Status.SCHEMA_ERROR
        request.error_message = f"Schema missing: {', '.join(missing)}"[:512]
        request.append_audit("schema_error", details={"missing": missing}, save=False)
        request.save(update_fields=["status", "error_message", "audit_trail"])
    return missing


def user_can_apply_live(*, user, membership) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    return bool(membership and membership.role.code == "invest_admin")


@transaction.atomic
def request_smev_fill(
    *,
    site: InvestSite,
    user,
    service: str = InvestSmevRequest.Service.EGRN,
    correlation_id: str | None = None,
    async_mode: bool = False,
) -> InvestSmevRequest:
    """Creates SMEV request; mock fills immediately unless live or async_mode."""
    ensure_default_info_types()
    cfg = ensure_automation_config(site.subsystem)
    correlation_id = correlation_id or _new_ids()[0]
    message_id = _new_ids()[1]
    timeout_at = timezone.now() + timedelta(hours=24)
    live = bool(cfg.flag("smev_live") and not cfg.flag("smev_mock"))

    if live or async_mode:
        req = InvestSmevRequest.objects.create(
            subsystem=site.subsystem,
            site=site,
            service=service,
            status=InvestSmevRequest.Status.LIVE_PENDING if live else InvestSmevRequest.Status.QUEUED,
            is_mock=not live,
            correlation_id=correlation_id,
            message_id=message_id,
            timeout_at=timeout_at,
            created_by=user,
            request_payload={
                "cadastral_number": site.cadastral_number,
                "service": service,
                "delay_seconds": 0,
            },
            response_payload={
                "note": "live SMEV request is pending; production gateway adapter is not connected in this build"
                if live
                else "queued for emulator"
            },
        )
        req.append_audit("request", actor=user, details={"mode": "live" if live else "async"}, save=True)
        site.last_smev_at = timezone.now()
        site.save(update_fields=["last_smev_at", "updated_at"])
        return req

    if service != InvestSmevRequest.Service.EGRN:
        payload = _mock_stub_payload(service, site.cadastral_number)
        req = InvestSmevRequest.objects.create(
            subsystem=site.subsystem,
            site=site,
            service=service,
            status=InvestSmevRequest.Status.DONE,
            is_mock=True,
            correlation_id=correlation_id,
            message_id=message_id,
            timeout_at=timeout_at,
            created_by=user,
            request_payload={"cadastral_number": site.cadastral_number, "service": service},
            response_payload=payload,
            finished_at=timezone.now(),
        )
        req.append_audit("request", actor=user, details={"service": service}, save=True)
        site.last_smev_at = timezone.now()
        site.save(update_fields=["last_smev_at", "updated_at"])
        return req

    payload = _mock_egrn_payload(site.cadastral_number)
    req = InvestSmevRequest.objects.create(
        subsystem=site.subsystem,
        site=site,
        service=InvestSmevRequest.Service.EGRN,
        status=InvestSmevRequest.Status.DONE,
        is_mock=True,
        correlation_id=correlation_id,
        message_id=message_id,
        timeout_at=timeout_at,
        created_by=user,
        request_payload={"cadastral_number": site.cadastral_number, "service": "egrn"},
        response_payload=payload,
        finished_at=timezone.now(),
    )
    req.append_audit("request", actor=user, details={"service": "egrn"}, save=True)
    site.last_smev_at = timezone.now()
    site.save(update_fields=["last_smev_at", "updated_at"])
    return req


@transaction.atomic
def request_contour_check(*, site: InvestSite, user) -> list[InvestSmevRequest]:
    correlation_id, _ = _new_ids()
    return [
        request_smev_fill(site=site, user=user, service=service, correlation_id=correlation_id)
        for service in (
            InvestSmevRequest.Service.EGRN,
            InvestSmevRequest.Service.ISOGD,
            InvestSmevRequest.Service.RGIS,
        )
    ]


@transaction.atomic
def batch_smev_requests(*, sites, user, service: str = InvestSmevRequest.Service.EGRN) -> dict:
    batch_id = uuid.uuid4().hex[:16]
    correlation_id = f"batch-{batch_id}"
    created = []
    for site in sites:
        req = request_smev_fill(site=site, user=user, service=service, correlation_id=correlation_id)
        created.append(req)
    summary = {
        "batch_id": batch_id,
        "correlation_id": correlation_id,
        "total": len(created),
        "done": sum(1 for r in created if r.status == InvestSmevRequest.Status.DONE),
        "pending": sum(
            1
            for r in created
            if r.status in (InvestSmevRequest.Status.QUEUED, InvestSmevRequest.Status.LIVE_PENDING)
        ),
        "error": sum(
            1
            for r in created
            if r.status
            in (
                InvestSmevRequest.Status.ERROR,
                InvestSmevRequest.Status.SCHEMA_ERROR,
                InvestSmevRequest.Status.DEAD_LETTER,
            )
        ),
        "applied": sum(1 for r in created if r.status == InvestSmevRequest.Status.APPLIED),
    }
    return summary


@transaction.atomic
def emulate_gateway_response(request: InvestSmevRequest, *, actor=None) -> InvestSmevRequest:
    delay = int((request.request_payload or {}).get("delay_seconds") or 0)
    if request.service == InvestSmevRequest.Service.EGRN:
        payload = _mock_egrn_payload(request.site.cadastral_number)
    else:
        payload = _mock_stub_payload(request.service, request.site.cadastral_number)
    payload["emulated_delay_seconds"] = delay
    payload["emulated_at"] = timezone.now().isoformat()
    request.response_payload = payload
    request.status = InvestSmevRequest.Status.DONE
    request.finished_at = timezone.now()
    request.error_message = ""
    request.append_audit("emulate", actor=actor, details={"delay_seconds": delay}, save=False)
    request.save(update_fields=["response_payload", "status", "finished_at", "error_message", "audit_trail"])
    return request


def _maybe_stop_factor(*, site: InvestSite, encumbrances: str, actor=None) -> None:
    text = (encumbrances or "").lower()
    if not any(token in text for token in CRITICAL_ENCUMBRANCE_KEYWORDS):
        return
    site.external_ids = {
        **(site.external_ids or {}),
        "smev_stop_factor": True,
        "smev_stop_factor_reason": encumbrances[:255],
    }
    site.save(update_fields=["external_ids", "updated_at"])
    for link in site.project_links.select_related("project"):
        InvestStopFactor.objects.get_or_create(
            project=link.project,
            title=f"СМЭВ: критичное обременение ({site.cadastral_number})",
            defaults={"status": InvestStopFactor.Status.BLOCKING},
        )


def _mark_package_egrn(*, site: InvestSite) -> None:
    for link in site.project_links.select_related("project"):
        package = ensure_package(link.project)
        item, _ = InvestPackageItem.objects.get_or_create(
            package=package,
            code="egrn_smev",
            defaults={
                "title": "Ответ СМЭВ ЕГРН",
                "required": True,
                "status": InvestPackageItem.Status.MISSING,
            },
        )
        item.status = InvestPackageItem.Status.ATTACHED
        item.save(update_fields=["status"])
        egrn = package.items.filter(code="egrn").first()
        if egrn and egrn.status == InvestPackageItem.Status.MISSING:
            egrn.status = InvestPackageItem.Status.ATTACHED
            egrn.save(update_fields=["status"])


@transaction.atomic
def apply_smev_response(
    *,
    request: InvestSmevRequest,
    user=None,
    fields: list[str] | None = None,
    rejected_fields: list[str] | None = None,
) -> InvestSite:
    if request.status not in (
        InvestSmevRequest.Status.DONE,
        InvestSmevRequest.Status.APPLIED,
    ):
        raise InvestSmevError("Нет готового ответа для применения")
    if request.service != InvestSmevRequest.Service.EGRN:
        raise InvestSmevError("Автозаполнение пока только для ЕГРН")
    if not request.is_mock:
        # Caller must enforce admin; keep defensive check for service use.
        pass

    data = dict(request.response_payload or {})
    rejected_fields = list(rejected_fields or data.get("rejected_fields") or [])
    selected = list(fields) if fields is not None else [f for f in APPLY_FIELDS if f not in rejected_fields]
    selected = [f for f in selected if f in APPLY_FIELDS and f not in rejected_fields]

    site = request.site
    before = {field: getattr(site, field) for field in APPLY_FIELDS}

    for field in selected:
        value = data.get(field)
        if value in (None, ""):
            continue
        if field in {"area_ha", "latitude", "longitude"}:
            setattr(site, field, Decimal(str(value)))
        else:
            setattr(site, field, value)

    after = {field: getattr(site, field) for field in APPLY_FIELDS}
    field_diff = {
        field: {"old": _diff_value(before[field]), "new": _diff_value(after[field])}
        for field in APPLY_FIELDS
        if _diff_value(before[field]) != _diff_value(after[field])
    }

    site.egrn_updated_at = timezone.now()
    site.last_smev_at = timezone.now()
    filled = sum(
        1
        for v in (
            site.address,
            site.area_ha,
            site.land_category,
            site.vri,
            site.right_type,
            site.latitude,
            site.longitude,
        )
        if v
    )
    site.completeness_pct = min(100, 40 + filled * 8)
    if site.status == InvestSite.Status.DRAFT:
        site.status = InvestSite.Status.IN_REVIEW
    site.external_ids = {
        **(site.external_ids or {}),
        "last_smev_request_id": request.pk,
        "smev_mock": bool(request.is_mock),
        "smev_rgis_intersections": data.get("zone_info")
        or "Mock-пересечения РГИС: уточнить по слою",
    }
    site.save()

    _maybe_stop_factor(site=site, encumbrances=site.encumbrances or "", actor=user)
    _mark_package_egrn(site=site)

    request.status = InvestSmevRequest.Status.APPLIED
    request.response_payload = {
        **data,
        "field_diff": field_diff,
        "applied_fields": selected,
        "rejected_fields": rejected_fields,
    }
    request.append_audit("apply", actor=user, details={"fields": selected}, save=False)
    if rejected_fields:
        request.append_audit("reject", actor=user, details={"fields": rejected_fields}, save=False)
    request.save(update_fields=["status", "response_payload", "audit_trail"])
    return site


def build_smev_report(*, subsystem, days: int = 7) -> dict:
    since = timezone.now() - timedelta(days=days)
    qs = InvestSmevRequest.objects.filter(subsystem=subsystem, created_at__gte=since)
    success = qs.filter(status__in=(InvestSmevRequest.Status.DONE, InvestSmevRequest.Status.APPLIED)).count()
    error = qs.filter(
        status__in=(
            InvestSmevRequest.Status.ERROR,
            InvestSmevRequest.Status.SCHEMA_ERROR,
            InvestSmevRequest.Status.DEAD_LETTER,
            InvestSmevRequest.Status.TIMEOUT,
        )
    ).count()
    finished = qs.exclude(finished_at=None)
    avg_seconds = None
    if finished.exists():
        # Average (finished_at - created_at) in seconds via Python for portability.
        deltas = [(r.finished_at - r.created_at).total_seconds() for r in finished if r.finished_at]
        avg_seconds = round(sum(deltas) / len(deltas), 1) if deltas else None
    top_mo = list(
        qs.filter(
            status__in=(
                InvestSmevRequest.Status.ERROR,
                InvestSmevRequest.Status.SCHEMA_ERROR,
                InvestSmevRequest.Status.DEAD_LETTER,
            )
        )
        .values("site__organization__name")
        .annotate(errors=Count("id"))
        .order_by("-errors")[:5]
    )
    return {
        "days": days,
        "total": qs.count(),
        "success": success,
        "error": error,
        "avg_seconds": avg_seconds,
        "top_mo_errors": top_mo,
    }


def render_smev_protocol_pdf(request: InvestSmevRequest) -> HttpResponse:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 48
    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(48, y, "SMEV request protocol")
    y -= 28
    pdf.setFont("Helvetica", 10)
    rows = [
        ("ID", str(request.pk)),
        ("Service", request.get_service_display()),
        ("Status", request.get_status_display()),
        ("Mode", request.mode_label),
        ("Correlation", request.correlation_id or "-"),
        ("Message", request.message_id or "-"),
        ("Cadastral", request.site.cadastral_number),
        ("Created", request.created_at.isoformat() if request.created_at else "-"),
        ("Finished", request.finished_at.isoformat() if request.finished_at else "-"),
    ]
    for label, value in rows:
        pdf.drawString(48, y, f"{label}: {value}"[:110])
        y -= 16
        if y < 64:
            pdf.showPage()
            y = height - 48
            pdf.setFont("Helvetica", 10)
    y -= 8
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(48, y, "Audit trail")
    y -= 16
    pdf.setFont("Helvetica", 9)
    for event in request.audit_trail or []:
        line = f"{event.get('created_at', '')} · {event.get('action')} · {event.get('actor', '')}"
        pdf.drawString(48, y, line[:110])
        y -= 14
        if y < 64:
            pdf.showPage()
            y = height - 48
            pdf.setFont("Helvetica", 9)
    pdf.showPage()
    pdf.save()
    payload = buffer.getvalue()
    response = HttpResponse(payload, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="smev-{request.pk}.pdf"'
    return response
