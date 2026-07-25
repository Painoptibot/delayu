"""Mock СМЭВ для демо инвестконтура (без промышленного шлюза)."""
from __future__ import annotations

import hashlib
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from delayu.models_invest import InvestSite, InvestSmevRequest
from delayu.services.invest_flags import ensure_automation_config


class InvestSmevError(Exception):
    pass


def _diff_value(value):
    if value is None:
        return None
    return str(value)


def _mock_egrn_payload(cadastral_number: str) -> dict:
    """Детерминированный ответ по кадастру — удобно для повторных демо."""
    digest = hashlib.sha1(cadastral_number.encode("utf-8")).hexdigest()
    area = Decimal((int(digest[:4], 16) % 9000) + 1000) / Decimal("100")  # 10.00–99.99 га
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


@transaction.atomic
def request_smev_fill(*, site: InvestSite, user, service: str = InvestSmevRequest.Service.EGRN) -> InvestSmevRequest:
    """Создаёт mock-запрос и сразу заполняет ответ (тестовый контур)."""
    cfg = ensure_automation_config(site.subsystem)
    if cfg.flag("smev_live") and not cfg.flag("smev_mock"):
        req = InvestSmevRequest.objects.create(
            subsystem=site.subsystem,
            site=site,
            service=service,
            status=InvestSmevRequest.Status.LIVE_PENDING,
            is_mock=False,
            created_by=user,
            request_payload={"cadastral_number": site.cadastral_number, "service": service},
            response_payload={
                "note": "live SMEV request is pending; production gateway adapter is not connected in this build"
            },
        )
        site.last_smev_at = timezone.now()
        site.save(update_fields=["last_smev_at", "updated_at"])
        return req

    if service != InvestSmevRequest.Service.EGRN:
        # Для демо достаточно ЕГРН; остальные сервисы — заглушки статуса
        req = InvestSmevRequest.objects.create(
            subsystem=site.subsystem,
            site=site,
            service=service,
            status=InvestSmevRequest.Status.DONE,
            is_mock=True,
            created_by=user,
            request_payload={"cadastral_number": site.cadastral_number},
            response_payload={"note": "Mock-ответ сервиса (поля в карточку не применялись)"},
            finished_at=timezone.now(),
        )
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
        created_by=user,
        request_payload={"cadastral_number": site.cadastral_number, "service": "egrn"},
        response_payload=payload,
        finished_at=timezone.now(),
    )
    site.last_smev_at = timezone.now()
    site.save(update_fields=["last_smev_at", "updated_at"])
    return req


@transaction.atomic
def apply_smev_response(*, request: InvestSmevRequest, user=None) -> InvestSite:
    """Переносит mock-ответ ЕГРН в карточку площадки."""
    if request.status not in (
        InvestSmevRequest.Status.DONE,
        InvestSmevRequest.Status.APPLIED,
    ):
        raise InvestSmevError("Нет готового ответа для применения")
    if request.service != InvestSmevRequest.Service.EGRN:
        raise InvestSmevError("Автозаполнение пока только для ЕГРН")
    data = request.response_payload or {}
    site = request.site
    before = {
        "address": site.address,
        "land_category": site.land_category,
        "vri": site.vri,
        "right_type": site.right_type,
        "encumbrances": site.encumbrances,
        "zone_info": site.zone_info,
        "area_ha": site.area_ha,
        "latitude": site.latitude,
        "longitude": site.longitude,
    }
    site.address = data.get("address") or site.address
    site.land_category = data.get("land_category") or site.land_category
    site.vri = data.get("vri") or site.vri
    site.right_type = data.get("right_type") or site.right_type
    site.encumbrances = data.get("encumbrances", site.encumbrances)
    site.zone_info = data.get("zone_info") or site.zone_info
    if data.get("area_ha"):
        site.area_ha = Decimal(str(data["area_ha"]))
    if data.get("latitude"):
        site.latitude = Decimal(str(data["latitude"]))
    if data.get("longitude"):
        site.longitude = Decimal(str(data["longitude"]))
    after = {
        "address": site.address,
        "land_category": site.land_category,
        "vri": site.vri,
        "right_type": site.right_type,
        "encumbrances": site.encumbrances,
        "zone_info": site.zone_info,
        "area_ha": site.area_ha,
        "latitude": site.latitude,
        "longitude": site.longitude,
    }
    field_diff = {
        field: {"old": _diff_value(before[field]), "new": _diff_value(after[field])}
        for field in before
        if _diff_value(before[field]) != _diff_value(after[field])
    }
    site.egrn_updated_at = timezone.now()
    site.last_smev_at = timezone.now()
    # Простая оценка полноты после автозаполнения
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
        "smev_mock": True,
    }
    site.save()
    request.status = InvestSmevRequest.Status.APPLIED
    request.response_payload = {**data, "field_diff": field_diff}
    request.save(update_fields=["status", "response_payload"])
    return site
