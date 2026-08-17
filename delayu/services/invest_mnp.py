"""Proxy helpers for МНП / ФГИС ТП (WMS raster + JSP GeoJSON vector).

Public GeoServer WFS is disabled; genplan polygons live in
``geo_db_data_fgistp_*`` WMS layers (CQL by ``uin``) and in viewapp JSP APIs.
"""
from __future__ import annotations

import logging
import math
import re
from typing import Any
from urllib.parse import urlparse

import httpx
from django.conf import settings
from django.core.cache import cache

from delayu.services.invest_flags import ensure_automation_config

logger = logging.getLogger(__name__)

DEFAULT_MNP_WMS_URL = "https://mnp.economy.gov.ru/geoserver/min_eco_test/wms"
DEFAULT_MNP_WFS_URL = "https://mnp.economy.gov.ru/geoserver/min_eco_test/wfs"
DEFAULT_MNP_JSP_BASE = "https://mnp.economy.gov.ru/geo/geomnp/viewapp/"
DEFAULT_MNP_WMS_LAYERS = "geo_db_data_fgistp_pol"
DEFAULT_MNP_WFS_TYPENAMES = "geo_db_data_fgistp_pol"  # legacy setting name
DEFAULT_MNP_VIEWER_URL = "https://mnp.economy.gov.ru/geo/geomnp/viewapp/index.html"
DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_FEATURES = 800
DEFAULT_MAX_SCHEMES = 6
# Prefer functional / land-use zones for vector overlay.
DEFAULT_VECTOR_CLASSIDS = (
    "701010101",
    "701010200",
    "701010301",
    "701010401",
    "701010500",
    "701010600",
    "701010700",
    "701010800",
    "701010900",
)

_BBOX_RE = re.compile(
    r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$"
)
_UIN_RE = re.compile(r"^[0-9A-Za-z]{8,64}$")
_CLASSID_RE = re.compile(r"^[0-9A-Za-z]{3,32}$")
_STP_CACHE_KEY = "invest_mnp_stp_list_v1"
_STP_CACHE_TTL = 3600
_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_EARTH_RADIUS = 20037508.342789244


class InvestMnpError(Exception):
    pass


def mnp_map_config(subsystem=None) -> dict[str, Any]:
    opts: dict = {}
    if subsystem is not None:
        opts = (ensure_automation_config(subsystem).options or {}).get("mnp_genplan") or {}
    vector_classids = opts.get("vector_classids") or getattr(
        settings, "INVEST_MNP_VECTOR_CLASSIDS", ""
    )
    if isinstance(vector_classids, str):
        vector_classids = [p.strip() for p in vector_classids.split(",") if p.strip()]
    if not vector_classids:
        vector_classids = list(DEFAULT_VECTOR_CLASSIDS)
    return {
        "wms_url": getattr(settings, "INVEST_MNP_WMS_URL", "") or opts.get("wms_url") or DEFAULT_MNP_WMS_URL,
        "wfs_url": getattr(settings, "INVEST_MNP_WFS_URL", "") or opts.get("wfs_url") or DEFAULT_MNP_WFS_URL,
        "jsp_base": getattr(settings, "INVEST_MNP_JSP_BASE", "") or opts.get("jsp_base") or DEFAULT_MNP_JSP_BASE,
        "wms_layers": opts.get("wms_layers")
        or getattr(settings, "INVEST_MNP_WMS_LAYERS", "")
        or DEFAULT_MNP_WMS_LAYERS,
        "wfs_typenames": opts.get("wfs_typenames")
        or getattr(settings, "INVEST_MNP_WFS_TYPENAMES", "")
        or DEFAULT_MNP_WFS_TYPENAMES,
        "vector_classids": vector_classids,
        "viewer_url": opts.get("viewer_url") or DEFAULT_MNP_VIEWER_URL,
        "timeout": float(opts.get("timeout") or getattr(settings, "INVEST_MNP_TIMEOUT", DEFAULT_TIMEOUT)),
        "max_features": int(
            opts.get("max_features") or getattr(settings, "INVEST_MNP_MAX_FEATURES", DEFAULT_MAX_FEATURES)
        ),
        "max_schemes": int(
            opts.get("max_schemes") or getattr(settings, "INVEST_MNP_MAX_SCHEMES", DEFAULT_MAX_SCHEMES)
        ),
        "enabled": bool(opts.get("enabled", True)),
    }


def _assert_allowed_upstream(url: str) -> None:
    host = (urlparse(url).hostname or "").lower()
    if host in {"mnp.economy.gov.ru", "localhost", "127.0.0.1"}:
        return
    configured = {
        (urlparse(mnp_map_config()["wms_url"]).hostname or "").lower(),
        (urlparse(mnp_map_config()["wfs_url"]).hostname or "").lower(),
        (urlparse(mnp_map_config()["jsp_base"]).hostname or "").lower(),
    }
    if host not in configured:
        raise InvestMnpError("Недопустимый upstream host для МНП proxy")


def validate_bbox(bbox: str) -> str:
    value = (bbox or "").strip().replace(" ", "")
    if not _BBOX_RE.match(value):
        raise InvestMnpError("Некорректный bbox")
    parts = [float(p) for p in value.split(",")]
    minx, miny, maxx, maxy = parts
    if minx >= maxx or miny >= maxy:
        raise InvestMnpError("bbox: min должен быть меньше max")
    if abs(maxx - minx) > 40 or abs(maxy - miny) > 40:
        raise InvestMnpError("bbox слишком большой")
    return value


def lonlat_to_mercator(lon: float, lat: float) -> tuple[float, float]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    x = lon * _EARTH_RADIUS / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    y = y * _EARTH_RADIUS / 180.0
    return x, y


def mercator_to_lonlat(x: float, y: float) -> tuple[float, float]:
    lon = x * 180.0 / _EARTH_RADIUS
    lat = y * 180.0 / _EARTH_RADIUS
    lat = 180.0 / math.pi * (2.0 * math.atan(math.exp(lat * math.pi / 180.0)) - math.pi / 2.0)
    return lon, lat


def bbox4326_to_3857(bbox: str) -> tuple[float, float, float, float]:
    min_lon, min_lat, max_lon, max_lat = [float(p) for p in bbox.split(",")]
    x1, y1 = lonlat_to_mercator(min_lon, min_lat)
    x2, y2 = lonlat_to_mercator(max_lon, max_lat)
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def _ogc_exception_message(content: bytes) -> str | None:
    text = content.decode("utf-8", errors="replace")
    if "Service WFS is disabled" in text:
        return "WFS на стороне МНП отключён"
    for pat in (
        r"<ServiceException[^>]*>(.*?)</ServiceException>",
        r"<ows:ExceptionText>(.*?)</ows:ExceptionText>",
        r"<ExceptionText>(.*?)</ExceptionText>",
    ):
        m = re.search(pat, text, re.I | re.S)
        if m:
            msg = re.sub(r"\s+", " ", m.group(1)).strip()
            if msg:
                return msg[:240]
    if "ServiceException" in text or "ExceptionReport" in text:
        return "МНП вернул ошибку OGC"
    return None


def _http_get(url: str, *, params: dict | None = None, timeout: float) -> httpx.Response:
    _assert_allowed_upstream(url)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            return client.get(url, params=params)
    except httpx.TimeoutException as exc:
        raise InvestMnpError("Таймаут запроса к МНП") from exc
    except httpx.HTTPError as exc:
        raise InvestMnpError(f"Ошибка сети МНП: {exc}") from exc


def fetch_stp_list(*, subsystem=None, force: bool = False) -> list[dict]:
    """Catalogue of ДТП schemes from MNP viewapp JSP (cached)."""
    cfg = mnp_map_config(subsystem)
    if not force:
        cached = cache.get(_STP_CACHE_KEY)
        if isinstance(cached, list):
            return cached
    base = cfg["jsp_base"].rstrip("/") + "/"
    url = base + "JSP/json_stp_list.jsp"
    response = _http_get(
        url,
        params={"fdate": "2010-1-1", "tdate": "2030-1-1", "sub": ""},
        timeout=max(cfg["timeout"], 40.0),
    )
    if response.status_code >= 400:
        raise InvestMnpError(f"Каталог схем МНП HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvestMnpError("Каталог схем МНП вернул не JSON") from exc
    rows = payload.get("stp_list") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise InvestMnpError("Некорректный каталог схем МНП")
    cache.set(_STP_CACHE_KEY, rows, _STP_CACHE_TTL)
    return rows


def _parse_extent(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = str(raw).split("_")
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(p) for p in parts)
    except ValueError:
        return None
    # Skip extents that look like lon/lat mixed into mercator fields.
    if abs(x1) < 180 and abs(x2) < 180 and abs(y1) < 90 and abs(y2) < 90:
        return None
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


# Reject RF-wide / broken extents (meters in EPSG:3857).
_MAX_SCHEME_SPAN_M = 1_800_000.0


def schemes_intersecting_bbox(
    bbox: str,
    *,
    subsystem=None,
    limit: int | None = None,
) -> list[dict]:
    bbox = validate_bbox(bbox)
    minx, miny, maxx, maxy = bbox4326_to_3857(bbox)
    center_x = (minx + maxx) / 2.0
    center_y = (miny + maxy) / 2.0
    cfg = mnp_map_config(subsystem)
    limit = max(1, min(int(limit or cfg["max_schemes"]), 20))
    hits: list[tuple[tuple, dict]] = []
    for row in fetch_stp_list(subsystem=subsystem):
        ext = _parse_extent(row.get("stp_extent"))
        if not ext:
            continue
        x1, y1, x2, y2 = ext
        span_x, span_y = x2 - x1, y2 - y1
        if span_x <= 0 or span_y <= 0:
            continue
        if span_x > _MAX_SCHEME_SPAN_M or span_y > _MAX_SCHEME_SPAN_M:
            continue
        if x2 < minx or x1 > maxx or y2 < miny or y1 > maxy:
            continue
        overlap = (min(maxx, x2) - max(minx, x1)) * (min(maxy, y2) - max(miny, y1))
        if overlap <= 0:
            continue
        uin = str(row.get("uin") or "")
        if not _UIN_RE.match(uin):
            continue
        contains_center = x1 <= center_x <= x2 and y1 <= center_y <= y2
        scheme_cx = (x1 + x2) / 2.0
        scheme_cy = (y1 + y2) / 2.0
        dist2 = (scheme_cx - center_x) ** 2 + (scheme_cy - center_y) ** 2
        scheme_area = span_x * span_y
        # Prefer schemes whose centroid is near the map center (avoids oversized
        # neighbouring municipal extents that still "contain" the point).
        rank = (0 if contains_center else 1, dist2, scheme_area, -overlap)
        hits.append((rank, row))
    hits.sort(key=lambda item: item[0])
    return [row for _, row in hits[:limit]]


def build_cql_for_uins(uins: list[str]) -> str | None:
    clean = [u for u in uins if _UIN_RE.match(u)]
    if not clean:
        return None
    if len(clean) == 1:
        return f"uin='{clean[0]}'"
    inner = ",".join(f"'{u}'" for u in clean)
    return f"uin IN ({inner})"


def fetch_mnp_wms_upstream(
    *,
    bbox: str,
    width: int = 256,
    height: int = 256,
    srs: str = "EPSG:4326",
    subsystem=None,
    cql_filter: str | None = None,
) -> tuple[bytes, str]:
    """Upstream GetMap for sync_mnp_kk only (not used by map runtime)."""
    cfg = mnp_map_config(subsystem)
    if not cfg["enabled"]:
        raise InvestMnpError("Слой МНП отключён")
    bbox = validate_bbox(bbox)
    width = max(64, min(int(width or 256), 1024))
    height = max(64, min(int(height or 256), 1024))
    srs = srs if srs in ("EPSG:4326", "EPSG:3857") else "EPSG:4326"
    upstream = cfg["wms_url"]
    _assert_allowed_upstream(upstream)

    if not cql_filter:
        schemes = schemes_intersecting_bbox(bbox, subsystem=subsystem)
        cql_filter = build_cql_for_uins([str(s.get("uin")) for s in schemes])
    if not cql_filter:
        return _TRANSPARENT_PNG, "image/png"

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": cfg["wms_layers"],
        "STYLES": "",
        "SRS": srs,
        "BBOX": bbox,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "TRANSPARENT": "true",
        "CQL_FILTER": cql_filter,
    }
    response = _http_get(upstream, params=params, timeout=cfg["timeout"])
    content_type = response.headers.get("content-type", "image/png")
    if response.status_code >= 400:
        raise InvestMnpError(f"WMS МНП HTTP {response.status_code}")
    ogc_err = _ogc_exception_message(response.content)
    if ogc_err or "xml" in content_type or response.content[:5] == b"<?xml":
        raise InvestMnpError(ogc_err or "WMS МНП вернул ошибку (XML)")
    return response.content, content_type.split(";")[0] or "image/png"


def fetch_mnp_wms(
    *,
    bbox: str,
    width: int = 256,
    height: int = 256,
    srs: str = "EPSG:4326",
    subsystem=None,
    cql_filter: str | None = None,
) -> tuple[bytes, str]:
    """Runtime compat: no upstream — prefer XYZ local tiles endpoint."""
    del width, height, srs, subsystem, cql_filter
    validate_bbox(bbox)
    return _TRANSPARENT_PNG, "image/png"


def _reproject_coords(obj: Any) -> Any:
    if isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], (int, float)):
        if len(obj) >= 2:
            lon, lat = mercator_to_lonlat(float(obj[0]), float(obj[1]))
            return [lon, lat]
        return list(obj)
    if isinstance(obj, list):
        return [_reproject_coords(item) for item in obj]
    return obj


def _reproject_feature(feature: dict) -> dict | None:
    geom = feature.get("geometry")
    if not isinstance(geom, dict):
        return None
    coords = geom.get("coordinates")
    if coords is None:
        return None
    props = feature.get("properties") if isinstance(feature.get("properties"), dict) else {}
    # JSP often puts attrs on the feature root.
    for key in ("naim", "id", "tp_stat", "reg_stat", "globalid", "layer_table_name", "number"):
        if key in feature and key not in props:
            props[key] = feature[key]
    name = props.get("naim") or props.get("mt_name") or props.get("name") or "Объект МНП"
    return {
        "type": "Feature",
        "id": feature.get("id"),
        "properties": {**props, "name": name},
        "geometry": {
            "type": geom.get("type"),
            "coordinates": _reproject_coords(coords),
        },
    }


def _fetch_layer_list(uin: str, *, subsystem=None) -> list[dict]:
    cfg = mnp_map_config(subsystem)
    base = cfg["jsp_base"].rstrip("/") + "/"
    response = _http_get(
        base + "JSP/json_layers_stp_list.jsp",
        params={"uin": uin},
        timeout=cfg["timeout"],
    )
    if response.status_code >= 400:
        raise InvestMnpError(f"Список слоёв МНП HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvestMnpError("Список слоёв МНП вернул не JSON") from exc
    rows = payload.get("layer_stp_list") if isinstance(payload, dict) else None
    return rows if isinstance(rows, list) else []


def _pick_vector_classid(layers: list[dict], preferred: list[str]) -> tuple[str, str] | None:
    polys = [l for l in layers if str(l.get("geom_type") or "") == "100"]
    by_id = {str(l.get("classid")): l for l in polys if l.get("classid")}
    for classid in preferred:
        if classid in by_id:
            return classid, "100"
    # Fallback: first land-use-ish (701*) then any polygon.
    for classid, layer in by_id.items():
        if classid.startswith("701"):
            return classid, str(layer.get("geom_type") or "100")
    if polys:
        layer = polys[0]
        return str(layer.get("classid")), str(layer.get("geom_type") or "100")
    return None


def _fetch_stp_features(
    *,
    uin: str,
    classid: str,
    geom_type: str = "100",
    subsystem=None,
) -> list[dict]:
    if not _UIN_RE.match(uin) or not _CLASSID_RE.match(classid):
        raise InvestMnpError("Некорректные параметры слоя МНП")
    cfg = mnp_map_config(subsystem)
    base = cfg["jsp_base"].rstrip("/") + "/"
    response = _http_get(
        base + "JSP/json_stp_layer_obj_list.jsp",
        params={
            "uin": uin,
            "obj_code": classid,
            "geom_type": geom_type,
            "st_code": "-1",
            "reg_code": "-1",
        },
        timeout=max(cfg["timeout"], 45.0),
    )
    if response.status_code >= 400:
        raise InvestMnpError(f"Объекты МНП HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise InvestMnpError("Объекты МНП вернули не JSON") from exc
    if isinstance(payload, dict) and payload.get("error_report"):
        raise InvestMnpError(f"МНП: {payload.get('error_report')}")
    features = payload.get("features") if isinstance(payload, dict) else None
    return features if isinstance(features, list) else []


def fetch_mnp_wfs(
    *,
    bbox: str,
    subsystem=None,
    max_features: int | str | None = None,
) -> dict:
    """Runtime: GeoJSON from local store only (no upstream)."""
    del subsystem
    from delayu.services.invest_mnp_store import query_features_geojson

    return query_features_geojson(bbox=bbox, max_features=max_features)
