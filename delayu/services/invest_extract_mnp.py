"""Extract contour × local MNP genplan intersections (no PostGIS)."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from delayu.models_invest import InvestExtract, InvestMnpFeature, InvestStopFactor
from delayu.services.invest_extracts import InvestExtractError
from delayu.services.invest_mnp_styles import style_for_classid

logger = logging.getLogger(__name__)

MNP_STOP_PREFIX = "Генплан МНП:"


def hard_classids() -> set[str]:
    raw = getattr(
        settings,
        "INVEST_MNP_EXTRACT_HARD_CLASSIDS",
        "701010800,701010301",
    )
    if isinstance(raw, (list, tuple, set)):
        return {str(x).strip() for x in raw if str(x).strip()}
    return {p.strip() for p in str(raw or "").split(",") if p.strip()}


def _as_geometry(obj: dict | None) -> dict | None:
    if not obj or not isinstance(obj, dict):
        return None
    if obj.get("type") == "Feature":
        return obj.get("geometry") if isinstance(obj.get("geometry"), dict) else None
    if obj.get("type") == "FeatureCollection":
        feats = obj.get("features") or []
        if not feats:
            return None
        return _as_geometry(feats[0] if isinstance(feats[0], dict) else None)
    return obj


def geometry_rings(geometry: dict | None) -> list[list[tuple[float, float]]]:
    """Outer rings as list of (lon, lat) rings."""
    geom = _as_geometry(geometry)
    if not geom:
        return []
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    if not coords:
        return []
    rings: list[list[tuple[float, float]]] = []

    def as_ring(raw) -> list[tuple[float, float]]:
        out: list[tuple[float, float]] = []
        for pair in raw or []:
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                out.append((float(pair[0]), float(pair[1])))
        return out

    if gtype == "Polygon":
        ring = as_ring(coords[0] if coords else [])
        if len(ring) >= 3:
            rings.append(ring)
    elif gtype == "MultiPolygon":
        for poly in coords:
            ring = as_ring((poly or [None])[0] or [])
            if len(ring) >= 3:
                rings.append(ring)
    return rings


def ring_bbox(ring: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]
    return min(lons), min(lats), max(lons), max(lats)


def geometry_bbox(geometry: dict | None) -> tuple[float, float, float, float] | None:
    rings = geometry_rings(geometry)
    if not rings:
        return None
    boxes = [ring_bbox(r) for r in rings]
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _point_in_ring(lon: float, lat: float, ring: list[tuple[float, float]]) -> bool:
    """Ray casting; ring in (lon, lat)."""
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersect = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if intersect:
            inside = not inside
        j = i
    return inside


def _orient(ax, ay, bx, by, cx, cy) -> float:
    return (by - ay) * (cx - bx) - (bx - ax) * (cy - by)


def _on_segment(ax, ay, bx, by, cx, cy) -> bool:
    return (
        min(ax, cx) - 1e-12 <= bx <= max(ax, cx) + 1e-12
        and min(ay, cy) - 1e-12 <= by <= max(ay, cy) + 1e-12
    )


def _segments_intersect(a1, a2, b1, b2) -> bool:
    o1 = _orient(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1])
    o2 = _orient(a1[0], a1[1], a2[0], a2[1], b2[0], b2[1])
    o3 = _orient(b1[0], b1[1], b2[0], b2[1], a1[0], a1[1])
    o4 = _orient(b1[0], b1[1], b2[0], b2[1], a2[0], a2[1])
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if abs(o1) < 1e-12 and _on_segment(a1[0], a1[1], b1[0], b1[1], a2[0], a2[1]):
        return True
    if abs(o2) < 1e-12 and _on_segment(a1[0], a1[1], b2[0], b2[1], a2[0], a2[1]):
        return True
    if abs(o3) < 1e-12 and _on_segment(b1[0], b1[1], a1[0], a1[1], b2[0], b2[1]):
        return True
    if abs(o4) < 1e-12 and _on_segment(b1[0], b1[1], a2[0], a2[1], b2[0], b2[1]):
        return True
    return False


def rings_intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    aa = ring_bbox(a)
    bb = ring_bbox(b)
    if aa[2] < bb[0] or bb[2] < aa[0] or aa[3] < bb[1] or bb[3] < aa[1]:
        return False
    for lon, lat in a:
        if _point_in_ring(lon, lat, b):
            return True
    for lon, lat in b:
        if _point_in_ring(lon, lat, a):
            return True
    for i in range(len(a) - 1):
        for j in range(len(b) - 1):
            if _segments_intersect(a[i], a[i + 1], b[j], b[j + 1]):
                return True
    # closed edges
    if _segments_intersect(a[-1], a[0], b[-1], b[0]):
        return True
    for i in range(len(a) - 1):
        if _segments_intersect(a[i], a[i + 1], b[-1], b[0]):
            return True
    for j in range(len(b) - 1):
        if _segments_intersect(a[-1], a[0], b[j], b[j + 1]):
            return True
    return False


def geometries_intersect(a: dict | None, b: dict | None) -> bool:
    rings_a = geometry_rings(a)
    rings_b = geometry_rings(b)
    for ra in rings_a:
        for rb in rings_b:
            if rings_intersect(ra, rb):
                return True
    return False


def find_mnp_intersections(geometry: dict | None, *, limit: int = 80) -> dict[str, Any]:
    """Return intersecting local MNP features for extract GeoJSON geometry."""
    bbox = geometry_bbox(geometry)
    hard = hard_classids()
    empty = {
        "computed_at": timezone.now().isoformat(),
        "count": 0,
        "hard_count": 0,
        "zones": [],
    }
    if not bbox:
        return empty
    min_lon, min_lat, max_lon, max_lat = bbox
    qs = (
        InvestMnpFeature.objects.filter(
            bbox_min_lon__lte=max_lon,
            bbox_max_lon__gte=min_lon,
            bbox_min_lat__lte=max_lat,
            bbox_max_lat__gte=min_lat,
        )
        .select_related("scheme")
        .order_by("id")[: max(50, min(int(limit) * 4, 400))]
    )
    zones: list[dict[str, Any]] = []
    for row in qs:
        if not geometries_intersect(geometry, row.geometry):
            continue
        props = dict(row.properties or {})
        style = style_for_classid(row.classid)
        is_hard = str(row.classid) in hard
        zones.append(
            {
                "feature_id": row.pk,
                "classid": row.classid,
                "label": style.get("label") or row.class_name or "Зона",
                "fill": style.get("fill") or "#7367f0",
                "name": props.get("name") or props.get("naim") or row.class_name or "Объект МНП",
                "uin": row.scheme.uin if row.scheme_id else "",
                "stp_name": row.scheme.name if row.scheme_id else "",
                "hard": is_hard,
            }
        )
        if len(zones) >= limit:
            break
    return {
        "computed_at": timezone.now().isoformat(),
        "count": len(zones),
        "hard_count": sum(1 for z in zones if z.get("hard")),
        "zones": zones,
    }


def _sync_mnp_stop_factors(extract: InvestExtract, snapshot: dict[str, Any]) -> None:
    hard_count = int(snapshot.get("hard_count") or 0)
    site = extract.site
    title = f"{MNP_STOP_PREFIX} конфликт зон ({site.cadastral_number})"
    for link in site.project_links.select_related("project"):
        project = link.project
        if hard_count > 0:
            InvestStopFactor.objects.get_or_create(
                project=project,
                title=title,
                defaults={
                    "status": InvestStopFactor.Status.BLOCKING,
                },
            )
        else:
            for sf in InvestStopFactor.objects.filter(
                project=project,
                title=title,
                status__in=(InvestStopFactor.Status.OPEN, InvestStopFactor.Status.BLOCKING),
            ):
                sf.status = InvestStopFactor.Status.RESOLVED
                sf.resolved_at = timezone.now()
                sf.save(update_fields=["status", "resolved_at"])


def refresh_extract_mnp_intersections(extract: InvestExtract) -> dict[str, Any]:
    """Compute intersections, store on extract.external_ids, sync stop-factors."""
    if not extract.geometry:
        snapshot = {
            "computed_at": timezone.now().isoformat(),
            "count": 0,
            "hard_count": 0,
            "zones": [],
            "empty_reason": "no_geometry",
        }
    else:
        try:
            snapshot = find_mnp_intersections(extract.geometry)
        except Exception as exc:  # noqa: BLE001
            logger.exception("MNP intersection failed extract=%s", extract.pk)
            raise InvestExtractError(f"Не удалось рассчитать пересечения с генпланом: {exc}") from exc
    ext = dict(extract.external_ids or {})
    ext["mnp_intersections"] = snapshot
    extract.external_ids = ext
    extract.save(update_fields=["external_ids", "updated_at"])
    try:
        _sync_mnp_stop_factors(extract, snapshot)
    except Exception:  # noqa: BLE001
        logger.exception("MNP stop-factor sync failed extract=%s", extract.pk)
    return snapshot


def intersections_from_extract(extract: InvestExtract) -> dict[str, Any]:
    data = (extract.external_ids or {}).get("mnp_intersections")
    if isinstance(data, dict):
        return data
    return {"computed_at": None, "count": 0, "hard_count": 0, "zones": []}
