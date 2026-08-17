"""Выкопировки инвестплощадок: lifecycle, mock-контур, пакет, стоп-факторы."""
from __future__ import annotations

import json
import math
import re
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from delayu.models_invest import (
    InvestExtract,
    InvestExternalTask,
    InvestPackageItem,
    InvestSite,
    InvestStopFactor,
)
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_package import ensure_package


class InvestExtractError(Exception):
    pass


ACTIVE_STATUSES = (
    InvestExtract.Status.DRAFT,
    InvestExtract.Status.REQUESTED,
    InvestExtract.Status.RECEIVED,
    InvestExtract.Status.VERIFIED,
    InvestExtract.Status.ATTACHED,
)

MAP_READY_STATUSES = (
    InvestExtract.Status.VERIFIED,
    InvestExtract.Status.ATTACHED,
    InvestExtract.Status.RECEIVED,
)

SLA_DAYS = 5
GEOJSON_MAX_BYTES = 2 * 1024 * 1024
STOP_TITLE_PREFIX = "Выкопировка:"


def _default_title(site: InvestSite, extract_type: str) -> str:
    label = dict(InvestExtract.ExtractType.choices).get(extract_type, extract_type)
    return f"{label} · {site.cadastral_number}"


def _stop_title(site: InvestSite, reason: str) -> str:
    return f"{STOP_TITLE_PREFIX} {reason} ({site.cadastral_number})"


def site_has_map_geometry(site: InvestSite) -> bool:
    return InvestExtract.objects.filter(
        site=site,
        status__in=MAP_READY_STATUSES,
    ).exclude(geometry={}).exists()


def latest_map_extract(site: InvestSite) -> InvestExtract | None:
    return (
        InvestExtract.objects.filter(site=site, status__in=MAP_READY_STATUSES)
        .exclude(geometry={})
        .order_by("-verified_at", "-updated_at", "-id")
        .first()
    )


def geojson_ring_to_yandex_coords(geometry: dict | None) -> list[list[float]]:
    """GeoJSON [lon, lat] → Yandex [lat, lon] ring."""
    if not geometry:
        return []
    geom = geometry
    if geom.get("type") == "Feature":
        geom = geom.get("geometry") or {}
    if geom.get("type") == "FeatureCollection":
        features = geom.get("features") or []
        if not features:
            return []
        geom = (features[0] or {}).get("geometry") or {}
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return []
    if gtype == "Polygon":
        ring = coords[0]
    elif gtype == "MultiPolygon":
        ring = coords[0][0]
    else:
        return []
    out = []
    for pair in ring:
        if not isinstance(pair, (list, tuple)) or len(pair) < 2:
            continue
        lon, lat = float(pair[0]), float(pair[1])
        out.append([lat, lon])
    return out


def extract_geometry_for_map(extract: InvestExtract | None) -> dict | None:
    if not extract or not extract.geometry:
        return None
    coords = geojson_ring_to_yandex_coords(extract.geometry)
    if len(coords) < 3:
        return None
    return {
        "coords": coords,
        "name": extract.title or extract.cadastral_number or "Выкопировка",
        "extractId": extract.pk,
        "source": extract.geometry_source,
    }


def generate_mock_contour_geojson(site: InvestSite, *, half_side_deg: float = 0.001) -> dict:
    if site.latitude is None or site.longitude is None:
        raise InvestExtractError("Для mock-контура нужны координаты площадки")
    lat = float(site.latitude)
    lon = float(site.longitude)
    # Compensate longitude degree length roughly by latitude.
    lon_scale = max(0.2, math.cos(math.radians(lat)))
    dlat = half_side_deg
    dlon = half_side_deg / lon_scale
    ring = [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]
    return {
        "type": "Polygon",
        "coordinates": [ring],
    }


def _parse_geojson_payload(raw: str | bytes | dict) -> dict:
    if isinstance(raw, dict):
        data = raw
    else:
        text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
        if len(text.encode("utf-8")) > GEOJSON_MAX_BYTES:
            raise InvestExtractError("GeoJSON слишком большой (лимит 2 МБ)")
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvestExtractError("Некорректный JSON") from exc
    if not isinstance(data, dict):
        raise InvestExtractError("Ожидается GeoJSON-объект")
    if data.get("type") == "Feature":
        geom = data.get("geometry")
        if not isinstance(geom, dict):
            raise InvestExtractError("Feature без geometry")
        return geom
    if data.get("type") == "FeatureCollection":
        features = data.get("features") or []
        if not features:
            raise InvestExtractError("Пустой FeatureCollection")
        geom = (features[0] or {}).get("geometry")
        if not isinstance(geom, dict):
            raise InvestExtractError("Feature без geometry")
        return geom
    if data.get("type") in ("Polygon", "MultiPolygon"):
        return data
    raise InvestExtractError("Поддерживаются Polygon / MultiPolygon / Feature / FeatureCollection")


def _parse_simple_kml(raw: str | bytes) -> dict:
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    if len(text.encode("utf-8")) > GEOJSON_MAX_BYTES:
        raise InvestExtractError("KML слишком большой (лимит 2 МБ)")
    match = re.search(
        r"<coordinates[^>]*>(.*?)</coordinates>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise InvestExtractError("В KML не найден блок coordinates")
    points = []
    for token in re.split(r"\s+", match.group(1).strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon, lat = float(parts[0]), float(parts[1])
        except ValueError as exc:
            raise InvestExtractError("Некорректные координаты KML") from exc
        points.append([lon, lat])
    if len(points) < 3:
        raise InvestExtractError("В KML меньше 3 точек полигона")
    if points[0] != points[-1]:
        points.append(points[0])
    return {"type": "Polygon", "coordinates": [points]}


def import_geometry_payload(raw: str | bytes, *, filename: str = "") -> dict:
    name = (filename or "").lower()
    if isinstance(raw, (bytes, bytearray)):
        head = raw[:200].lower()
        is_kml = name.endswith(".kml") or b"<kml" in head
    else:
        head = str(raw)[:200].lower()
        is_kml = name.endswith(".kml") or "<kml" in head
    if is_kml:
        return _parse_simple_kml(raw)
    return _parse_geojson_payload(raw)


def _mark_package_extract(*, site: InvestSite, project=None) -> None:
    links = site.project_links.select_related("project")
    if project is not None:
        links = links.filter(project=project)
    for link in links:
        package = ensure_package(link.project)
        item, _ = InvestPackageItem.objects.get_or_create(
            package=package,
            code="extract",
            defaults={
                "title": "Выкопировка / ситуационный план",
                "required": True,
                "status": InvestPackageItem.Status.MISSING,
            },
        )
        item.status = InvestPackageItem.Status.ATTACHED
        item.save(update_fields=["status"])


def _raise_or_clear_stop_factors(*, site: InvestSite, missing: bool, expired: bool) -> None:
    for link in site.project_links.select_related("project"):
        project = link.project
        if missing:
            InvestStopFactor.objects.get_or_create(
                project=project,
                title=_stop_title(site, "отсутствует"),
                defaults={"status": InvestStopFactor.Status.BLOCKING},
            )
        if expired:
            InvestStopFactor.objects.get_or_create(
                project=project,
                title=_stop_title(site, "просрочена"),
                defaults={"status": InvestStopFactor.Status.BLOCKING},
            )
        if not missing and not expired:
            for sf in InvestStopFactor.objects.filter(
                project=project,
                title__startswith=STOP_TITLE_PREFIX,
                status__in=(InvestStopFactor.Status.OPEN, InvestStopFactor.Status.BLOCKING),
            ).filter(title__contains=site.cadastral_number):
                sf.status = InvestStopFactor.Status.RESOLVED
                sf.resolved_at = timezone.now()
                sf.save(update_fields=["status", "resolved_at"])


def _ensure_mo_task(*, extract: InvestExtract, user=None) -> None:
    project = extract.project
    if project is None:
        link = extract.site.project_links.select_related("project").order_by("id").first()
        if not link:
            return
        project = link.project
        extract.project = project
        extract.save(update_fields=["project", "updated_at"])
    title = f"Выкопировка: {extract.site.cadastral_number}"
    existing = InvestExternalTask.objects.filter(
        project=project,
        kind=InvestExternalTask.Kind.MO,
        title=title,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).first()
    if existing:
        return
    InvestExternalTask.objects.create(
        subsystem=extract.subsystem,
        project=project,
        organization=extract.site.organization,
        kind=InvestExternalTask.Kind.MO,
        status=InvestExternalTask.Status.OPEN,
        title=title,
        due_at=extract.sla_due_at,
        response_payload={"extract_id": extract.pk, "reason": (extract.external_ids or {}).get("request_reason", "")},
    )


@transaction.atomic
def ensure_extract_for_site(
    site: InvestSite,
    *,
    reason: str = "",
    user=None,
    project=None,
    extract_type: str = InvestExtract.ExtractType.SITUATIONAL,
    force: bool = False,
) -> InvestExtract | None:
    if not force and not flag_enabled(site.subsystem, "auto_extract", default=True):
        return None
    active = (
        InvestExtract.objects.filter(site=site, status__in=ACTIVE_STATUSES)
        .exclude(status=InvestExtract.Status.EXPIRED)
        .order_by("-updated_at")
        .first()
    )
    if active and active.status in (
        InvestExtract.Status.VERIFIED,
        InvestExtract.Status.ATTACHED,
        InvestExtract.Status.RECEIVED,
        InvestExtract.Status.REQUESTED,
    ):
        return active

    now = timezone.now()
    extract = active
    if extract is None or extract.status in (InvestExtract.Status.DRAFT, InvestExtract.Status.REJECTED):
        if extract is None:
            extract = InvestExtract(
                subsystem=site.subsystem,
                site=site,
                project=project,
                extract_type=extract_type,
            )
        extract.cadastral_number = site.cadastral_number
        extract.title = extract.title or _default_title(site, extract_type)
        extract.status = InvestExtract.Status.REQUESTED
        extract.requested_at = now
        extract.requested_by = user if getattr(user, "is_authenticated", False) else None
        extract.sla_due_at = now + timedelta(days=SLA_DAYS)
        extract.external_ids = {**(extract.external_ids or {}), "request_reason": reason}
        if project is not None:
            extract.project = project
        extract.save()
    else:
        return extract

    _ensure_mo_task(extract=extract, user=user)
    _raise_or_clear_stop_factors(site=site, missing=True, expired=False)
    return extract


@transaction.atomic
def mark_extract_received(extract: InvestExtract, *, user=None, uploaded_file=None) -> InvestExtract:
    if uploaded_file is not None:
        extract.file = uploaded_file
    extract.status = InvestExtract.Status.RECEIVED
    extract.received_at = timezone.now()
    update_fields = ["status", "received_at", "updated_at"]
    if uploaded_file is not None:
        update_fields.append("file")
    extract.save(update_fields=update_fields)
    return extract


@transaction.atomic
def verify_extract(extract: InvestExtract, *, user=None, attach: bool = True) -> InvestExtract:
    extract.status = InvestExtract.Status.VERIFIED
    extract.verified_at = timezone.now()
    extract.verified_by = user if getattr(user, "is_authenticated", False) else None
    extract.save(update_fields=["status", "verified_at", "verified_by", "updated_at"])
    _raise_or_clear_stop_factors(site=extract.site, missing=False, expired=False)
    from delayu.services.invest_extract_mnp import refresh_extract_mnp_intersections

    refresh_extract_mnp_intersections(extract)
    if attach:
        return attach_extract_to_package(extract, user=user)
    return extract


@transaction.atomic
def attach_extract_to_package(extract: InvestExtract, *, user=None) -> InvestExtract:
    _mark_package_extract(site=extract.site, project=extract.project)
    extract.status = InvestExtract.Status.ATTACHED
    extract.save(update_fields=["status", "updated_at"])
    _raise_or_clear_stop_factors(site=extract.site, missing=False, expired=False)
    # Close related MO tasks
    title = f"Выкопировка: {extract.site.cadastral_number}"
    InvestExternalTask.objects.filter(
        project__site_links__site=extract.site,
        kind=InvestExternalTask.Kind.MO,
        title=title,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).update(status=InvestExternalTask.Status.ANSWERED, answered_at=timezone.now())
    return extract


@transaction.atomic
def generate_mock_contour(extract: InvestExtract, *, user=None) -> InvestExtract:
    site = extract.site
    if site.latitude is None or site.longitude is None:
        # Place near Krasnodar for demo if missing.
        site.latitude = Decimal("45.035470")
        site.longitude = Decimal("38.975313")
        site.save(update_fields=["latitude", "longitude", "updated_at"])
    extract.geometry = generate_mock_contour_geojson(site)
    extract.geometry_source = InvestExtract.GeometrySource.MOCK
    if extract.status in (InvestExtract.Status.DRAFT, InvestExtract.Status.REQUESTED):
        extract.status = InvestExtract.Status.RECEIVED
        extract.received_at = timezone.now()
    stub = ContentFile(
        f"%PDF-1.4\n% Mock extract {extract.cadastral_number or site.cadastral_number}\n".encode("utf-8"),
        name=f"extract-{site.pk}-mock.pdf",
    )
    extract.file.save(stub.name, stub, save=False)
    extract.external_ids = {**(extract.external_ids or {}), "mock_contour": True}
    extract.save()
    from delayu.services.invest_extract_mnp import refresh_extract_mnp_intersections

    refresh_extract_mnp_intersections(extract)
    return extract


@transaction.atomic
def import_extract_geometry(extract: InvestExtract, *, raw: str | bytes, filename: str = "", user=None) -> InvestExtract:
    geom = import_geometry_payload(raw, filename=filename)
    extract.geometry = geom
    extract.geometry_source = InvestExtract.GeometrySource.IMPORT
    if extract.status in (InvestExtract.Status.DRAFT, InvestExtract.Status.REQUESTED):
        extract.status = InvestExtract.Status.RECEIVED
        extract.received_at = timezone.now()
    extract.save()
    from delayu.services.invest_extract_mnp import refresh_extract_mnp_intersections

    refresh_extract_mnp_intersections(extract)
    return extract


@transaction.atomic
def expire_extracts(*, subsystem=None, now=None) -> dict[str, int]:
    now = now or timezone.now()
    qs = InvestExtract.objects.filter(
        status__in=(
            InvestExtract.Status.REQUESTED,
            InvestExtract.Status.RECEIVED,
            InvestExtract.Status.VERIFIED,
            InvestExtract.Status.ATTACHED,
        )
    )
    if subsystem is not None:
        qs = qs.filter(subsystem=subsystem)

    expired_validity = 0
    overdue_sla = 0
    for extract in qs.select_related("site"):
        if extract.valid_until and extract.valid_until < now.date():
            extract.status = InvestExtract.Status.EXPIRED
            extract.save(update_fields=["status", "updated_at"])
            _raise_or_clear_stop_factors(site=extract.site, missing=False, expired=True)
            expired_validity += 1
            continue
        if (
            extract.status == InvestExtract.Status.REQUESTED
            and extract.sla_due_at
            and extract.sla_due_at < now
        ):
            _raise_or_clear_stop_factors(site=extract.site, missing=True, expired=False)
            overdue_sla += 1
    return {"expired": expired_validity, "overdue_sla": overdue_sla}


def maybe_request_extract_after_smev(*, site: InvestSite, user=None) -> InvestExtract | None:
    """If EGRN applied but no extract geometry — offer/request extract."""
    if site_has_map_geometry(site):
        return None
    return ensure_extract_for_site(site, reason="smev_egrn_no_geometry", user=user)


def extracts_for_inbox(*, projects, now=None):
    now = now or timezone.now()
    site_ids = set()
    for project in projects:
        site_ids.update(project.site_links.values_list("site_id", flat=True))
    return (
        InvestExtract.objects.filter(site_id__in=site_ids)
        .filter(
            status=InvestExtract.Status.REQUESTED,
            sla_due_at__lt=now,
        )
        .select_related("site", "site__organization", "project")
        .order_by("sla_due_at")[:50]
    )
