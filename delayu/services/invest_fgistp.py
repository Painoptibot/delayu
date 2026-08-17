"""Сведения ФГИС ТП: lifecycle, mock-зоны, пакет isogd, стоп-факторы."""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import models, transaction
from django.utils import timezone

from delayu.models_invest import (
    InvestExternalTask,
    InvestFgistpDocument,
    InvestFgistpRecord,
    InvestPackageItem,
    InvestSite,
    InvestStopFactor,
)
from delayu.services.invest_extracts import (
    InvestExtractError,
    generate_mock_contour_geojson,
    geojson_ring_to_yandex_coords,
    import_geometry_payload,
)
from delayu.services.invest_flags import flag_enabled
from delayu.services.invest_package import ensure_package


class InvestFgistpError(InvestExtractError):
    pass


ACTIVE_STATUSES = (
    InvestFgistpRecord.Status.DRAFT,
    InvestFgistpRecord.Status.REQUESTED,
    InvestFgistpRecord.Status.RECEIVED,
    InvestFgistpRecord.Status.VERIFIED,
    InvestFgistpRecord.Status.ATTACHED,
)

MAP_READY_STATUSES = (
    InvestFgistpRecord.Status.VERIFIED,
    InvestFgistpRecord.Status.ATTACHED,
    InvestFgistpRecord.Status.RECEIVED,
)

SLA_DAYS = 5
STOP_TITLE_PREFIX = "ФГИС ТП:"


def _default_title(site: InvestSite, record_type: str) -> str:
    label = dict(InvestFgistpRecord.RecordType.choices).get(record_type, record_type)
    return f"{label} · {site.cadastral_number}"


def _stop_title(site: InvestSite, reason: str) -> str:
    return f"{STOP_TITLE_PREFIX} {reason} ({site.cadastral_number})"


def site_has_fgistp_geometry(site: InvestSite) -> bool:
    return InvestFgistpRecord.objects.filter(
        site=site,
        status__in=MAP_READY_STATUSES,
    ).exclude(geometry={}).exists()


def latest_map_fgistp(site: InvestSite) -> InvestFgistpRecord | None:
    return (
        InvestFgistpRecord.objects.filter(site=site, status__in=MAP_READY_STATUSES)
        .exclude(geometry={})
        .order_by("-verified_at", "-updated_at", "-id")
        .first()
    )


def fgistp_geometry_for_map(record: InvestFgistpRecord | None) -> dict | None:
    if not record or not record.geometry:
        return None
    coords = geojson_ring_to_yandex_coords(record.geometry)
    if len(coords) < 3:
        return None
    return {
        "coords": coords,
        "name": record.title or record.cadastral_number or "ФГИС ТП",
        "recordId": record.pk,
        "source": record.geometry_source,
    }


def _mock_payload(site: InvestSite) -> dict:
    return {
        "source": "mock-fgistp",
        "zones": [
            {"name": "Зона производственного назначения", "code": "P-1", "restriction": "без ООПТ"},
            {"name": "Зона инженерной инфраструктуры", "code": "I-2", "restriction": "охранные зоны сетей"},
        ],
        "documents": [
            {
                "title": "Схема территориального планирования субъекта (mock)",
                "level": "regional",
                "uin": f"mock-{site.cadastral_number}",
            }
        ],
        "cadastral_number": site.cadastral_number,
        "note": "Demo-ответ ФГИС ТП без live WFS",
    }


def _mark_package_isogd(*, site: InvestSite, project=None) -> None:
    links = site.project_links.select_related("project")
    if project is not None:
        links = links.filter(project=project)
    for link in links:
        package = ensure_package(link.project)
        item, _ = InvestPackageItem.objects.get_or_create(
            package=package,
            code="isogd",
            defaults={
                "title": "Материалы ИСОГД",
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


def _ensure_mo_task(*, record: InvestFgistpRecord, user=None) -> None:
    project = record.project
    if project is None:
        link = record.site.project_links.select_related("project").order_by("id").first()
        if not link:
            return
        project = link.project
        record.project = project
        record.save(update_fields=["project", "updated_at"])
    title = f"ФГИС ТП: {record.site.cadastral_number}"
    existing = InvestExternalTask.objects.filter(
        project=project,
        kind=InvestExternalTask.Kind.MO,
        title=title,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).first()
    if existing:
        return
    InvestExternalTask.objects.create(
        subsystem=record.subsystem,
        project=project,
        organization=record.site.organization,
        kind=InvestExternalTask.Kind.MO,
        status=InvestExternalTask.Status.OPEN,
        title=title,
        due_at=record.sla_due_at,
        response_payload={"fgistp_id": record.pk, "reason": (record.external_ids or {}).get("request_reason", "")},
    )


@transaction.atomic
def ensure_fgistp_for_site(
    site: InvestSite,
    *,
    reason: str = "",
    user=None,
    project=None,
    record_type: str = InvestFgistpRecord.RecordType.ZONES,
    force: bool = False,
) -> InvestFgistpRecord | None:
    if not force and not flag_enabled(site.subsystem, "auto_fgistp", default=True):
        return None
    active = (
        InvestFgistpRecord.objects.filter(site=site, status__in=ACTIVE_STATUSES)
        .exclude(status=InvestFgistpRecord.Status.EXPIRED)
        .order_by("-updated_at")
        .first()
    )
    if active and active.status in (
        InvestFgistpRecord.Status.VERIFIED,
        InvestFgistpRecord.Status.ATTACHED,
        InvestFgistpRecord.Status.RECEIVED,
        InvestFgistpRecord.Status.REQUESTED,
    ):
        return active

    now = timezone.now()
    record = active
    if record is None or record.status in (InvestFgistpRecord.Status.DRAFT, InvestFgistpRecord.Status.REJECTED):
        if record is None:
            record = InvestFgistpRecord(
                subsystem=site.subsystem,
                site=site,
                project=project,
                record_type=record_type,
            )
        record.cadastral_number = site.cadastral_number
        record.title = record.title or _default_title(site, record_type)
        record.status = InvestFgistpRecord.Status.REQUESTED
        record.requested_at = now
        record.requested_by = user if getattr(user, "is_authenticated", False) else None
        record.sla_due_at = now + timedelta(days=SLA_DAYS)
        record.external_ids = {**(record.external_ids or {}), "request_reason": reason}
        if project is not None:
            record.project = project
        record.save()
    else:
        return record

    _ensure_mo_task(record=record, user=user)
    _raise_or_clear_stop_factors(site=site, missing=True, expired=False)
    return record


@transaction.atomic
def mark_fgistp_received(record: InvestFgistpRecord, *, user=None, uploaded_file=None) -> InvestFgistpRecord:
    if uploaded_file is not None:
        record.file = uploaded_file
    record.status = InvestFgistpRecord.Status.RECEIVED
    record.received_at = timezone.now()
    update_fields = ["status", "received_at", "updated_at"]
    if uploaded_file is not None:
        update_fields.append("file")
    record.save(update_fields=update_fields)
    return record


@transaction.atomic
def verify_fgistp(record: InvestFgistpRecord, *, user=None, attach: bool = True) -> InvestFgistpRecord:
    record.status = InvestFgistpRecord.Status.VERIFIED
    record.verified_at = timezone.now()
    record.verified_by = user if getattr(user, "is_authenticated", False) else None
    record.save(update_fields=["status", "verified_at", "verified_by", "updated_at"])
    _raise_or_clear_stop_factors(site=record.site, missing=False, expired=False)
    if attach:
        return attach_fgistp_to_package(record, user=user)
    return record


@transaction.atomic
def attach_fgistp_to_package(record: InvestFgistpRecord, *, user=None) -> InvestFgistpRecord:
    _mark_package_isogd(site=record.site, project=record.project)
    record.status = InvestFgistpRecord.Status.ATTACHED
    record.save(update_fields=["status", "updated_at"])
    _raise_or_clear_stop_factors(site=record.site, missing=False, expired=False)
    title = f"ФГИС ТП: {record.site.cadastral_number}"
    InvestExternalTask.objects.filter(
        project__site_links__site=record.site,
        kind=InvestExternalTask.Kind.MO,
        title=title,
        status__in=(InvestExternalTask.Status.OPEN, InvestExternalTask.Status.OVERDUE),
    ).update(status=InvestExternalTask.Status.ANSWERED, answered_at=timezone.now())
    return record


@transaction.atomic
def generate_mock_zones(record: InvestFgistpRecord, *, user=None) -> InvestFgistpRecord:
    site = record.site
    if site.latitude is None or site.longitude is None:
        site.latitude = Decimal("45.035470")
        site.longitude = Decimal("38.975313")
        site.save(update_fields=["latitude", "longitude", "updated_at"])
    # Slightly larger buffer than extracts to visually distinguish layers.
    record.geometry = generate_mock_contour_geojson(site, half_side_deg=0.0015)
    record.geometry_source = InvestFgistpRecord.GeometrySource.MOCK
    record.payload = _mock_payload(site)
    if record.status in (InvestFgistpRecord.Status.DRAFT, InvestFgistpRecord.Status.REQUESTED):
        record.status = InvestFgistpRecord.Status.RECEIVED
        record.received_at = timezone.now()
    stub = ContentFile(
        f"%PDF-1.4\n% Mock FGISTP {record.cadastral_number or site.cadastral_number}\n".encode("utf-8"),
        name=f"fgistp-{site.pk}-mock.pdf",
    )
    record.file.save(stub.name, stub, save=False)
    record.external_ids = {**(record.external_ids or {}), "mock_zones": True}
    record.save()
    return record


@transaction.atomic
def import_fgistp_geometry(
    record: InvestFgistpRecord, *, raw: str | bytes, filename: str = "", user=None
) -> InvestFgistpRecord:
    try:
        geom = import_geometry_payload(raw, filename=filename)
    except InvestExtractError as exc:
        raise InvestFgistpError(str(exc)) from exc
    record.geometry = geom
    record.geometry_source = InvestFgistpRecord.GeometrySource.IMPORT
    if record.status in (InvestFgistpRecord.Status.DRAFT, InvestFgistpRecord.Status.REQUESTED):
        record.status = InvestFgistpRecord.Status.RECEIVED
        record.received_at = timezone.now()
    record.save()
    return record


@transaction.atomic
def expire_fgistp_records(*, subsystem=None, now=None) -> dict[str, int]:
    now = now or timezone.now()
    qs = InvestFgistpRecord.objects.filter(
        status__in=(
            InvestFgistpRecord.Status.REQUESTED,
            InvestFgistpRecord.Status.RECEIVED,
            InvestFgistpRecord.Status.VERIFIED,
            InvestFgistpRecord.Status.ATTACHED,
        )
    )
    if subsystem is not None:
        qs = qs.filter(subsystem=subsystem)

    expired_validity = 0
    overdue_sla = 0
    for record in qs.select_related("site"):
        if record.valid_until and record.valid_until < now.date():
            record.status = InvestFgistpRecord.Status.EXPIRED
            record.save(update_fields=["status", "updated_at"])
            _raise_or_clear_stop_factors(site=record.site, missing=False, expired=True)
            expired_validity += 1
            continue
        if (
            record.status == InvestFgistpRecord.Status.REQUESTED
            and record.sla_due_at
            and record.sla_due_at < now
        ):
            _raise_or_clear_stop_factors(site=record.site, missing=True, expired=False)
            overdue_sla += 1
    return {"expired": expired_validity, "overdue_sla": overdue_sla}


def maybe_request_fgistp_after_smev(*, site: InvestSite, user=None) -> InvestFgistpRecord | None:
    if site_has_fgistp_geometry(site):
        return None
    return ensure_fgistp_for_site(site, reason="smev_egrn_no_fgistp", user=user)


def fgistp_for_inbox(*, projects, now=None):
    now = now or timezone.now()
    site_ids = set()
    for project in projects:
        site_ids.update(project.site_links.values_list("site_id", flat=True))
    return (
        InvestFgistpRecord.objects.filter(site_id__in=site_ids)
        .filter(
            status=InvestFgistpRecord.Status.REQUESTED,
            sla_due_at__lt=now,
        )
        .select_related("site", "site__organization", "project")
        .order_by("sla_due_at")[:50]
    )


# --- Demo catalog search -------------------------------------------------

_KN_RE = re.compile(r"^\d{2}:\d{2}:")


def normalize_cadastral(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").strip())


def looks_like_cadastral(value: str) -> bool:
    return bool(_KN_RE.match(normalize_cadastral(value)))


def search_fgistp_documents(
    *,
    subsystem,
    q: str = "",
    level: str = "",
    limit: int = 50,
) -> list[dict]:
    """Search demo FGISTP catalog by address or cadastral number."""
    q = (q or "").strip()
    qs = InvestFgistpDocument.objects.filter(is_active=True).filter(
        models.Q(subsystem=subsystem) | models.Q(subsystem__isnull=True)
    )
    # Prefer subsystem-scoped docs: filter in Python ranking if both exist
    if level:
        qs = qs.filter(level=level)

    docs = list(qs.order_by("title")[:500])
    if not q:
        return [
            {"document": doc, "score": 0, "match": "all"}
            for doc in docs[:limit]
        ]

    kn = normalize_cadastral(q)
    kn_mode = looks_like_cadastral(q)
    q_lower = q.lower()
    scored: list[dict] = []

    for doc in docs:
        numbers = [normalize_cadastral(str(n)) for n in (doc.cadastral_numbers or [])]
        score = 0
        match = ""
        if kn_mode or ":" in kn:
            if kn in numbers:
                score = 100
                match = "cadastral_exact"
            else:
                for num in numbers:
                    if num.startswith(kn) or kn.startswith(num) or kn[:11] == num[:11]:
                        score = max(score, 80)
                        match = "cadastral_prefix"
                        break
        address = (doc.address_text or "").lower()
        muni = (doc.municipality_name or "").lower()
        title = (doc.title or "").lower()
        if q_lower and (q_lower in address or q_lower in muni or q_lower in title):
            score = max(score, 50)
            if not match:
                match = "address"
        if score > 0:
            scored.append({"document": doc, "score": score, "match": match})

    scored.sort(key=lambda item: (-item["score"], item["document"].title))
    return scored[:limit]


@transaction.atomic
def attach_fgistp_document(
    *,
    document: InvestFgistpDocument,
    site: InvestSite,
    user=None,
    project=None,
) -> InvestFgistpRecord:
    if document.subsystem_id and document.subsystem_id != site.subsystem_id:
        raise InvestFgistpError("Документ принадлежит другому контуру")

    existing = (
        InvestFgistpRecord.objects.filter(site=site)
        .filter(external_ids__uin=document.uin)
        .order_by("-updated_at")
        .first()
    )
    # JSONField lookup may not work on all backends for nested; fallback scan
    if existing is None:
        for rec in InvestFgistpRecord.objects.filter(site=site).order_by("-updated_at")[:20]:
            if (rec.external_ids or {}).get("uin") == document.uin:
                existing = rec
                break

    record_type = InvestFgistpRecord.RecordType.DOCUMENT
    if (document.payload or {}).get("zones") or document.doc_type == InvestFgistpDocument.DocType.SCHEME:
        record_type = InvestFgistpRecord.RecordType.ZONES

    now = timezone.now()
    if existing:
        record = existing
    else:
        record = InvestFgistpRecord(
            subsystem=site.subsystem,
            site=site,
            project=project,
            record_type=record_type,
        )

    record.cadastral_number = site.cadastral_number
    record.title = document.title[:255]
    record.record_type = record_type
    record.status = InvestFgistpRecord.Status.RECEIVED
    record.received_at = now
    if record.requested_at is None:
        record.requested_at = now
        record.requested_by = user if getattr(user, "is_authenticated", False) else None
    record.payload = {
        **(document.payload or {}),
        "catalog_uin": document.uin,
        "catalog_level": document.level,
        "catalog_doc_type": document.doc_type,
        "source": "mock-fgistp-catalog",
    }
    if document.geometry:
        record.geometry = document.geometry
        record.geometry_source = InvestFgistpRecord.GeometrySource.MOCK
    record.external_ids = {
        **(record.external_ids or {}),
        "uin": document.uin,
        "fgistp_document_id": document.pk,
        "request_reason": "catalog_attach",
    }
    record.notes = f"Привязано из демо-каталога ФГИС ТП (UIN {document.uin})"
    if project is not None:
        record.project = project
    record.save()
    return record
