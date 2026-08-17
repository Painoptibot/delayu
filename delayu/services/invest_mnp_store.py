"""Local MNP tile/feature store for Krasnodar Krai (manual sync only)."""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from delayu.models_invest import InvestMnpFeature, InvestMnpScheme, InvestMnpSyncRun
from delayu.services.invest_mnp import (
    DEFAULT_VECTOR_CLASSIDS,
    InvestMnpError,
    _MAX_SCHEME_SPAN_M,
    _fetch_layer_list,
    _fetch_stp_features,
    _parse_extent,
    _pick_vector_classid,
    _reproject_feature,
    bbox4326_to_3857,
    build_cql_for_uins,
    fetch_mnp_wms_upstream,
    fetch_stp_list,
    mnp_map_config,
    validate_bbox,
)

logger = logging.getLogger(__name__)

_TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

# WGS84 eccentricity for Yandex elliptical mercator tiles.
_WGS84_E = 0.0818191908426


def region_code() -> str:
    return str(getattr(settings, "INVEST_MNP_REGION_CODE", "03") or "03")


def region_bbox() -> str:
    return validate_bbox(getattr(settings, "INVEST_MNP_REGION_BBOX", "36.5,43.5,40.5,47.0"))


def store_root() -> Path:
    configured = (getattr(settings, "INVEST_MNP_STORE_DIR", "") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(settings.MEDIA_ROOT) / "mnp_store"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tiles_root() -> Path:
    path = store_root() / "tiles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def viewport_cache_root() -> Path:
    path = store_root() / "viewports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def tile_path(z: int, x: int, y: int) -> Path:
    return tiles_root() / str(int(z)) / str(int(x)) / f"{int(y)}.png"


def quantize_bbox(bbox: str, *, zoom: int | None = None) -> str:
    """Snap bbox so nearby pans/zooms share a cache key."""
    bbox = validate_bbox(bbox)
    parts = [float(p) for p in bbox.split(",")]
    z = int(zoom) if zoom is not None else 12
    # Coarser snap → higher cache hit rate when panning.
    # z<=11: ~1.1km, z<=14: ~111m, else ~11m
    if z <= 11:
        decimals = 2
    elif z <= 14:
        decimals = 3
    else:
        decimals = 4
    return ",".join(f"{p:.{decimals}f}" for p in parts)


def _viewport_cache_key(
    *,
    bbox: str,
    width: int,
    height: int,
    mode: str,
    zoom: int | None,
) -> str:
    import hashlib

    raw = f"{bbox}|{int(width)}x{int(height)}|{mode}|{zoom if zoom is not None else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def read_viewport_cache(key: str) -> bytes | None:
    ttl = int(getattr(settings, "INVEST_MNP_VIEWPORT_CACHE_TTL", 3600))
    if ttl <= 0:
        return None
    path = viewport_cache_root() / f"{key}.png"
    if not path.is_file():
        return None
    try:
        age = timezone.now().timestamp() - path.stat().st_mtime
        if age > ttl:
            return None
        content = path.read_bytes()
        if content[:4] != b"\x89PNG":
            return None
        return content
    except OSError:
        return None


def write_viewport_cache(key: str, content: bytes) -> None:
    ttl = int(getattr(settings, "INVEST_MNP_VIEWPORT_CACHE_TTL", 3600))
    if ttl <= 0 or not content or content[:4] != b"\x89PNG":
        return
    # Skip 1×1 transparent placeholder only.
    if content == _TRANSPARENT_PNG or len(content) < 80:
        return
    path = viewport_cache_root() / f"{key}.png"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    except OSError:
        logger.exception("MNP viewport cache write failed %s", path)


def render_viewport_png(
    *,
    bbox: str,
    width: int = 256,
    height: int = 256,
    mode: str | None = None,
    zoom: int | str | None = None,
    allow_live: bool | None = None,
) -> bytes:
    """Compose viewport PNG: local tiles, GeoJSON vector draw, and optional live WMS.

    Modes:
      - tiles: local tile mosaic
      - vector: draw from local GeoJSON (sharp outlines)
      - detail/live: live MNP GetMap at viewport resolution (most detailed raster)
      - auto: tiles → at DETAIL_ZOOM prefer live WMS → else vector draw
    """
    bbox = validate_bbox(bbox)
    width = max(64, min(int(width or 256), 1600))
    height = max(64, min(int(height or 256), 1600))
    mode_raw = (mode or getattr(settings, "INVEST_MNP_VIEWPORT_MODE", "auto") or "auto").strip().lower()
    if mode_raw not in {"auto", "tiles", "vector", "detail", "live"}:
        mode_raw = "auto"
    try:
        zoom_i = int(zoom) if zoom not in (None, "") else None
    except (TypeError, ValueError):
        zoom_i = None

    # Snap bbox for cache hits across tiny pan deltas; use snapped bbox for rendering too.
    bbox_q = quantize_bbox(bbox, zoom=zoom_i)
    cache_key = _viewport_cache_key(
        bbox=bbox_q, width=width, height=height, mode=mode_raw, zoom=zoom_i
    )
    cached = read_viewport_cache(cache_key)
    if cached:
        return cached

    vector_zoom = int(getattr(settings, "INVEST_MNP_VECTOR_ZOOM", 11))
    detail_zoom = int(getattr(settings, "INVEST_MNP_DETAIL_ZOOM", 12))
    live_enabled = (
        bool(getattr(settings, "INVEST_MNP_LIVE_WMS", True))
        if allow_live is None
        else bool(allow_live)
    )

    want_detail = mode_raw in {"detail", "live"} or (
        mode_raw == "auto" and zoom_i is not None and zoom_i >= detail_zoom and live_enabled
    )
    result: bytes = _TRANSPARENT_PNG
    if want_detail and live_enabled:
        live = _live_wms_viewport_png(bbox=bbox_q, width=width, height=height)
        if _png_content_ratio(live) >= 0.002:
            result = live
            write_viewport_cache(cache_key, result)
            return result

    use_vector = mode_raw == "vector" or (
        mode_raw == "auto" and zoom_i is not None and zoom_i >= vector_zoom
    )
    if use_vector or want_detail:
        drawn = render_features_png(bbox=bbox_q, width=width, height=height)
        if _png_content_ratio(drawn) >= 0.002:
            result = drawn
            write_viewport_cache(cache_key, result)
            return result

    if mode_raw != "vector":
        tiled = _mosaic_local_tiles_png(bbox=bbox_q, width=width, height=height)
        if _png_content_ratio(tiled) >= 0.002:
            result = tiled
            write_viewport_cache(cache_key, result)
            return result

    drawn = render_features_png(bbox=bbox_q, width=width, height=height)
    if _png_content_ratio(drawn) >= 0.002:
        result = drawn
        write_viewport_cache(cache_key, result)
        return result

    if live_enabled and not want_detail:
        result = _live_wms_viewport_png(bbox=bbox_q, width=width, height=height)
        write_viewport_cache(cache_key, result)
        return result
    return _TRANSPARENT_PNG


def render_features_png(
    *,
    bbox: str,
    width: int = 256,
    height: int = 256,
    max_features: int | None = None,
) -> bytes:
    """Draw local GeoJSON features into a sharp PNG for the bbox."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise InvestMnpError("Pillow не установлен") from exc

    import io

    from delayu.services.invest_mnp_styles import style_for_classid

    bbox = validate_bbox(bbox)
    min_lon, min_lat, max_lon, max_lat = [float(p) for p in bbox.split(",")]
    width = max(64, min(int(width or 256), 1600))
    height = max(64, min(int(height or 256), 1600))
    span_lon = max(max_lon - min_lon, 1e-12)
    span_lat = max(max_lat - min_lat, 1e-12)
    limit = max_features
    if limit is None:
        limit = int(getattr(settings, "INVEST_MNP_MAX_FEATURES", 800))
    data = query_features_geojson(bbox=bbox, max_features=limit)
    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(out, "RGBA")

    def to_px(lon: float, lat: float) -> tuple[float, float]:
        x = (lon - min_lon) / span_lon * (width - 1)
        y = (max_lat - lat) / span_lat * (height - 1)
        return x, y

    def draw_ring(ring: list, *, fill, outline) -> None:
        pts = []
        for pair in ring or []:
            if not isinstance(pair, (list, tuple)) or len(pair) < 2:
                continue
            pts.append(to_px(float(pair[0]), float(pair[1])))
        if len(pts) >= 3:
            draw.polygon(pts, fill=fill, outline=outline)

    for feature in data.get("features") or []:
        geom = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        style = style_for_classid(props.get("classid"))
        fill = tuple(style["fill_rgba"])
        outline = tuple(style["stroke_rgba"])
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon":
            draw_ring(coords[0] if coords else [], fill=fill, outline=outline)
        elif gtype == "MultiPolygon":
            for poly in coords:
                draw_ring((poly or [None])[0] or [], fill=fill, outline=outline)
        elif gtype == "LineString":
            pts = [
                to_px(float(p[0]), float(p[1]))
                for p in coords
                if isinstance(p, (list, tuple)) and len(p) >= 2
            ]
            if len(pts) >= 2:
                draw.line(pts, fill=outline, width=2)

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _png_content_ratio(content: bytes) -> float:
    if not content or content[:4] != b"\x89PNG" or content == _TRANSPARENT_PNG:
        return 0.0
    try:
        from PIL import Image
        import io

        with Image.open(io.BytesIO(content)) as img:
            img = img.convert("RGBA")
            alphas = img.getchannel("A")
            hist = alphas.histogram()
            opaque = sum(hist[16:])  # alpha > 15
            total = max(1, img.size[0] * img.size[1])
            return opaque / total
    except Exception:  # noqa: BLE001
        return 0.0


def _mosaic_local_tiles_png(*, bbox: str, width: int, height: int) -> bytes:
    """Mosaic local tiles for a geographic bbox (map-projection agnostic)."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise InvestMnpError("Pillow не установлен") from exc

    import io

    min_lon, min_lat, max_lon, max_lat = [float(p) for p in bbox.split(",")]
    zmax = int(getattr(settings, "INVEST_MNP_TILE_ZMAX", 12))
    zmin = int(getattr(settings, "INVEST_MNP_TILE_ZMIN", 8))
    z = zmax
    center_lon = (min_lon + max_lon) / 2.0
    center_lat = (min_lat + max_lat) / 2.0
    for candidate in range(zmax, zmin - 1, -1):
        px, py = _lonlat_to_yandex_global_pixels(center_lon, center_lat, candidate)
        if tile_path(candidate, int(px // 256), int(py // 256)).is_file():
            z = candidate
            break

    west_x, north_y = _lonlat_to_yandex_global_pixels(min_lon, max_lat, z)
    east_x, south_y = _lonlat_to_yandex_global_pixels(max_lon, min_lat, z)
    if abs(east_x - west_x) < 1e-6 or abs(south_y - north_y) < 1e-6:
        return _TRANSPARENT_PNG

    x0 = int(math.floor(min(west_x, east_x) / 256))
    x1 = int(math.floor(max(west_x, east_x) / 256))
    y0 = int(math.floor(min(north_y, south_y) / 256))
    y1 = int(math.floor(max(north_y, south_y) / 256))
    if (x1 - x0 + 1) * (y1 - y0 + 1) > 64:
        z = max(zmin, z - 2)
        west_x, north_y = _lonlat_to_yandex_global_pixels(min_lon, max_lat, z)
        east_x, south_y = _lonlat_to_yandex_global_pixels(max_lon, min_lat, z)
        x0 = int(math.floor(min(west_x, east_x) / 256))
        x1 = int(math.floor(max(west_x, east_x) / 256))
        y0 = int(math.floor(min(north_y, south_y) / 256))
        y1 = int(math.floor(max(north_y, south_y) / 256))

    out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    span_x = east_x - west_x
    span_y = south_y - north_y

    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            path = tile_path(z, tx, ty)
            if not path.is_file():
                continue
            try:
                with Image.open(path) as tile_img:
                    tile_img = tile_img.convert("RGBA")
                    src_left = tx * 256
                    src_top = ty * 256
                    src_right = src_left + 256
                    src_bottom = src_top + 256
                    left = max(src_left, min(west_x, east_x))
                    right = min(src_right, max(west_x, east_x))
                    top = max(src_top, min(north_y, south_y))
                    bottom = min(src_bottom, max(north_y, south_y))
                    if right <= left or bottom <= top:
                        continue
                    crop = tile_img.crop(
                        (
                            int(left - src_left),
                            int(top - src_top),
                            int(math.ceil(right - src_left)),
                            int(math.ceil(bottom - src_top)),
                        )
                    )
                    dst_x0 = (left - west_x) / span_x * width
                    dst_x1 = (right - west_x) / span_x * width
                    dst_y0 = (top - north_y) / span_y * height
                    dst_y1 = (bottom - north_y) / span_y * height
                    dw = max(1, int(math.ceil(abs(dst_x1 - dst_x0))))
                    dh = max(1, int(math.ceil(abs(dst_y1 - dst_y0))))
                    resized = crop.resize((dw, dh), Image.Resampling.BILINEAR)
                    out.paste(resized, (int(dst_x0), int(dst_y0)), resized)
            except Exception:  # noqa: BLE001
                logger.exception("MNP viewport tile compose failed %s", path)
                continue

    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def _live_wms_viewport_png(*, bbox: str, width: int, height: int) -> bytes:
    """Fetch upstream WMS for bbox; optionally bake covering tiles into local store."""
    uins = _scheme_uins_for_tile_bbox(bbox, limit=12)
    cql = build_cql_for_uins(uins)
    if not cql:
        return _TRANSPARENT_PNG
    try:
        content, _ctype = fetch_mnp_wms_upstream(
            bbox=bbox,
            width=width,
            height=height,
            srs="EPSG:4326",
            cql_filter=cql,
        )
    except Exception:  # noqa: BLE001
        logger.exception("MNP live WMS viewport failed bbox=%s", bbox)
        return _TRANSPARENT_PNG
    if not content or content[:4] != b"\x89PNG":
        return _TRANSPARENT_PNG
    if bool(getattr(settings, "INVEST_MNP_LIVE_WMS_CACHE", True)):
        try:
            _cache_live_tiles_for_bbox(bbox)
        except Exception:  # noqa: BLE001
            logger.exception("MNP live tile cache failed bbox=%s", bbox)
    return content


def _cache_live_tiles_for_bbox(bbox: str) -> int:
    """Bake tiles covering bbox at high zoom (up to 16 tiles)."""
    z_store = int(getattr(settings, "INVEST_MNP_TILE_ZMAX", 12))
    z = min(max(z_store + 2, 14), 15)
    tiles = list(iter_yandex_tiles_for_bbox(bbox, zmin=z, zmax=z))
    if len(tiles) > 16:
        # Too wide — bake coarser zoom instead
        z = max(z_store, z - 1)
        tiles = list(iter_yandex_tiles_for_bbox(bbox, zmin=z, zmax=z))
        if len(tiles) > 16:
            return 0
    written = 0
    for _z, x, y in tiles:
        path = tile_path(_z, x, y)
        if path.is_file() and path.stat().st_size > 400:
            continue
        tile_bbox = yandex_tile_bbox_4326(_z, x, y)
        uins = _scheme_uins_for_tile_bbox(tile_bbox)
        cql = build_cql_for_uins(uins)
        if not cql:
            write_tile_bytes(_z, x, y, _TRANSPARENT_PNG)
            continue
        content, _ctype = fetch_mnp_wms_upstream(
            bbox=tile_bbox,
            width=256,
            height=256,
            srs="EPSG:4326",
            cql_filter=cql,
        )
        if not content or content[:4] != b"\x89PNG":
            content = _TRANSPARENT_PNG
        else:
            written += 1
        write_tile_bytes(_z, x, y, content)
    return written


def read_tile_bytes(z: int, x: int, y: int) -> bytes:
    """Return local tile; if missing at high zoom, overzoom from parent (z<=12 store)."""
    z, x, y = int(z), int(x), int(y)
    path = tile_path(z, x, y)
    if path.is_file():
        return path.read_bytes()
    return _overzoom_from_parent(z, x, y) or _TRANSPARENT_PNG


def _overzoom_from_parent(z: int, x: int, y: int) -> bytes | None:
    """Crop/scale parent tile so raster stays visible when map zoom > baked max."""
    try:
        from PIL import Image
    except ImportError:
        return None

    import io

    zmin = int(getattr(settings, "INVEST_MNP_TILE_ZMIN", 8))
    for pz in range(z - 1, zmin - 1, -1):
        diff = z - pz
        px = x >> diff
        py = y >> diff
        parent = tile_path(pz, px, py)
        if not parent.is_file():
            continue
        scale = 1 << diff
        ox = x - (px << diff)
        oy = y - (py << diff)
        try:
            with Image.open(parent) as img:
                img = img.convert("RGBA")
                w, h = img.size
                cell_w = w / scale
                cell_h = h / scale
                left = ox * cell_w
                top = oy * cell_h
                crop = img.crop(
                    (int(left), int(top), int(left + cell_w), int(top + cell_h))
                ).resize((256, 256), Image.Resampling.BILINEAR)
                buf = io.BytesIO()
                crop.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:  # noqa: BLE001
            logger.exception("MNP overzoom failed z=%s x=%s y=%s via %s", z, x, y, parent)
            return None
    return None


def write_tile_bytes(z: int, x: int, y: int, content: bytes) -> Path:
    path = tile_path(z, x, y)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def store_status() -> dict[str, Any]:
    schemes = InvestMnpScheme.objects.count()
    features = InvestMnpFeature.objects.count()
    last = InvestMnpSyncRun.objects.order_by("-started_at").first()
    tile_files = 0
    root = tiles_root()
    if root.exists():
        tile_files = sum(1 for _ in root.rglob("*.png"))
    return {
        "schemes": schemes,
        "features": features,
        "tiles": tile_files,
        "empty": schemes == 0 and features == 0 and tile_files == 0,
        "last_sync_at": last.finished_at.isoformat() if last and last.finished_at else None,
        "last_sync_ok": bool(last.ok) if last else None,
        "last_sync_stats": (last.stats if last else {}) or {},
        "region_code": region_code(),
        "region_bbox": region_bbox(),
    }


def filter_kk_schemes(rows: Iterable[dict], *, limit: int | None = None) -> list[dict]:
    """Keep Krasnodar Krai schemes: UIN prefix + extent ∩ region bbox."""
    code = region_code()
    minx, miny, maxx, maxy = bbox4326_to_3857(region_bbox())
    hits: list[dict] = []
    for row in rows:
        uin = str(row.get("uin") or "")
        if not uin.startswith(code):
            continue
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
        hits.append(row)
        if limit and len(hits) >= limit:
            break
    return hits


def geometry_bbox(geometry: dict | None) -> tuple[float, float, float, float] | None:
    if not geometry or not isinstance(geometry, dict):
        return None
    coords = geometry.get("coordinates")
    if coords is None:
        return None
    lons: list[float] = []
    lats: list[float] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, (list, tuple)) and obj and isinstance(obj[0], (int, float)):
            if len(obj) >= 2:
                lons.append(float(obj[0]))
                lats.append(float(obj[1]))
            return
        if isinstance(obj, list):
            for item in obj:
                walk(item)

    walk(coords)
    if not lons or not lats:
        return None
    return min(lons), min(lats), max(lons), max(lats)


def _rank_schemes_for_bbox(bbox: str, *, limit_schemes: int = 6) -> list[InvestMnpScheme]:
    """Prefer local schemes around map center (avoid early global id order)."""
    minx, miny, maxx, maxy = bbox4326_to_3857(bbox)
    center_x = (minx + maxx) / 2.0
    center_y = (miny + maxy) / 2.0
    candidates = list(
        InvestMnpScheme.objects.filter(status=InvestMnpScheme.Status.READY).filter(
            Q(extent_min_x__isnull=True)
            | (
                Q(extent_max_x__gte=minx)
                & Q(extent_min_x__lte=maxx)
                & Q(extent_max_y__gte=miny)
                & Q(extent_min_y__lte=maxy)
            )
        )
    )

    def rank(scheme: InvestMnpScheme) -> tuple:
        if scheme.extent_min_x is None:
            return (2, 1e99, 1e99)
        x1, y1 = scheme.extent_min_x, scheme.extent_min_y
        x2, y2 = scheme.extent_max_x, scheme.extent_max_y
        contains = x1 <= center_x <= x2 and y1 <= center_y <= y2
        area = max(1.0, (x2 - x1) * (y2 - y1))
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        dist2 = (cx - center_x) ** 2 + (cy - center_y) ** 2
        return (0 if contains else 1, dist2, area)

    candidates.sort(key=rank)
    return candidates[: max(1, min(int(limit_schemes), 20))]


def query_features_geojson(
    *,
    bbox: str,
    max_features: int | str | None = None,
) -> dict:
    bbox = validate_bbox(bbox)
    cfg = mnp_map_config()
    try:
        raw_limit = int(max_features) if max_features not in (None, "") else int(cfg["max_features"])
    except (TypeError, ValueError):
        raw_limit = int(cfg["max_features"])
    limit = max(1, min(raw_limit, 2000))
    min_lon, min_lat, max_lon, max_lat = [float(p) for p in bbox.split(",")]
    schemes = _rank_schemes_for_bbox(bbox, limit_schemes=max(3, min(cfg.get("max_schemes") or 6, 8)))
    features: list[dict] = []
    used_schemes: list[str] = []
    for scheme in schemes:
        if len(features) >= limit:
            break
        remaining = limit - len(features)
        qs = (
            InvestMnpFeature.objects.filter(
                scheme=scheme,
                bbox_min_lon__lte=max_lon,
                bbox_max_lon__gte=min_lon,
                bbox_min_lat__lte=max_lat,
                bbox_max_lat__gte=min_lat,
            )
            .order_by("id")[:remaining]
        )
        batch = 0
        for row in qs:
            props = dict(row.properties or {})
            props.setdefault("name", props.get("naim") or row.class_name or "Объект МНП")
            props["uin"] = scheme.uin
            props["stp_name"] = scheme.name
            props["classid"] = row.classid
            features.append(
                {
                    "type": "Feature",
                    "id": row.external_id or row.pk,
                    "properties": props,
                    "geometry": row.geometry,
                }
            )
            batch += 1
        if batch:
            used_schemes.append(scheme.uin)
    status = store_status()
    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "source": "mnp_local_store",
            "count": len(features),
            "schemes": used_schemes,
            "store": status,
        },
    }


@transaction.atomic
def upsert_scheme_features(
    *,
    uin: str,
    name: str,
    extent_raw: str,
    classid: str,
    class_name: str,
    geom_type: str,
    raw_features: list[dict],
) -> InvestMnpScheme:
    ext = _parse_extent(extent_raw)
    scheme, _ = InvestMnpScheme.objects.update_or_create(
        uin=uin,
        defaults={
            "name": name or uin,
            "extent_raw": extent_raw or "",
            "extent_min_x": ext[0] if ext else None,
            "extent_min_y": ext[1] if ext else None,
            "extent_max_x": ext[2] if ext else None,
            "extent_max_y": ext[3] if ext else None,
            "status": InvestMnpScheme.Status.PENDING,
            "error_text": "",
        },
    )
    InvestMnpFeature.objects.filter(scheme=scheme).delete()
    bulk: list[InvestMnpFeature] = []
    for feature in raw_features:
        if not isinstance(feature, dict):
            continue
        item = _reproject_feature(feature)
        if not item:
            continue
        geom = item.get("geometry") or {}
        bb = geometry_bbox(geom)
        if not bb:
            continue
        props = item.get("properties") or {}
        bulk.append(
            InvestMnpFeature(
                scheme=scheme,
                external_id=str(item.get("id") or props.get("id") or "")[:128],
                classid=classid,
                class_name=class_name or "",
                geom_type=geom_type or "",
                properties=props,
                geometry=geom,
                bbox_min_lon=bb[0],
                bbox_min_lat=bb[1],
                bbox_max_lon=bb[2],
                bbox_max_lat=bb[3],
            )
        )
    if bulk:
        InvestMnpFeature.objects.bulk_create(bulk, batch_size=500)
    scheme.feature_count = len(bulk)
    scheme.status = InvestMnpScheme.Status.READY
    scheme.synced_at = timezone.now()
    scheme.save(
        update_fields=["feature_count", "status", "synced_at", "error_text", "updated_at"]
    )
    return scheme


def sync_features(
    *,
    limit_schemes: int | None = None,
    progress=None,
) -> dict[str, Any]:
    cfg = mnp_map_config()
    preferred = cfg.get("vector_classids") or list(DEFAULT_VECTOR_CLASSIDS)
    rows = filter_kk_schemes(fetch_stp_list(force=True), limit=limit_schemes)
    stats = {"schemes_total": len(rows), "schemes_ok": 0, "schemes_error": 0, "features": 0}
    for idx, row in enumerate(rows, start=1):
        uin = str(row.get("uin") or "")
        name = str(row.get("stp_name") or "")
        if progress:
            progress(f"[{idx}/{len(rows)}] features {uin}")
        try:
            layers = _fetch_layer_list(uin)
            picked = _pick_vector_classid(layers, preferred)
            if not picked:
                raise InvestMnpError("Нет полигональных слоёв")
            classid, geom_type = picked
            class_name = ""
            for layer in layers:
                if str(layer.get("classid")) == classid and str(layer.get("geom_type")) == geom_type:
                    class_name = str(layer.get("class_name") or "")
                    break
            raw = _fetch_stp_features(uin=uin, classid=classid, geom_type=geom_type)
            scheme = upsert_scheme_features(
                uin=uin,
                name=name,
                extent_raw=str(row.get("stp_extent") or ""),
                classid=classid,
                class_name=class_name,
                geom_type=geom_type,
                raw_features=raw,
            )
            stats["schemes_ok"] += 1
            stats["features"] += scheme.feature_count
        except Exception as exc:  # noqa: BLE001 — collect per-scheme errors
            stats["schemes_error"] += 1
            logger.exception("MNP feature sync failed uin=%s", uin)
            InvestMnpScheme.objects.update_or_create(
                uin=uin,
                defaults={
                    "name": name or uin,
                    "extent_raw": str(row.get("stp_extent") or ""),
                    "status": InvestMnpScheme.Status.ERROR,
                    "error_text": str(exc)[:2000],
                },
            )
    return stats


def _lonlat_to_yandex_global_pixels(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """Yandex Maps elliptical mercator global pixel coordinates."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    world = 256 * (2**zoom)
    x = (lon + 180.0) / 360.0 * world
    lat_rad = math.radians(lat)
    e = _WGS84_E
    esin = e * math.sin(lat_rad)
    # Clamp asin arg
    esin = max(min(esin, 0.9999999999), -0.9999999999)
    tan_temp = math.tan(math.pi / 4.0 + lat_rad / 2.0)
    pow_temp = math.pow(math.tan(math.pi / 4.0 + math.asin(esin) / 2.0), e)
    y = (0.5 - math.log(tan_temp / pow_temp) / (2.0 * math.pi)) * world
    return x, y


def _yandex_global_pixels_to_lonlat(px: float, py: float, zoom: int) -> tuple[float, float]:
    world = 256 * (2**zoom)
    lon = px / world * 360.0 - 180.0
    y = 0.5 - py / world
    e = _WGS84_E
    ts = math.exp(-2.0 * math.pi * y)
    phi = math.pi / 2.0 - 2.0 * math.atan(ts)
    for _ in range(15):
        con = e * math.sin(phi)
        dphi = (
            math.pi / 2.0
            - 2.0 * math.atan(ts * math.pow((1.0 - con) / (1.0 + con), e / 2.0))
            - phi
        )
        phi += dphi
        if abs(dphi) < 1e-10:
            break
    return lon, math.degrees(phi)


def yandex_tile_bbox_4326(z: int, x: int, y: int) -> str:
    """BBox west,south,east,north for a Yandex tile (matches frontend Layer)."""
    sw_lon, sw_lat = _yandex_global_pixels_to_lonlat(x * 256, (y + 1) * 256, z)
    ne_lon, ne_lat = _yandex_global_pixels_to_lonlat((x + 1) * 256, y * 256, z)
    return f"{min(sw_lon, ne_lon)},{min(sw_lat, ne_lat)},{max(sw_lon, ne_lon)},{max(sw_lat, ne_lat)}"


def iter_yandex_tiles_for_bbox(
    bbox: str,
    *,
    zmin: int,
    zmax: int,
) -> Iterable[tuple[int, int, int]]:
    min_lon, min_lat, max_lon, max_lat = [float(p) for p in validate_bbox(bbox).split(",")]
    for z in range(int(zmin), int(zmax) + 1):
        px0, py_ne = _lonlat_to_yandex_global_pixels(min_lon, max_lat, z)
        px1, py_sw = _lonlat_to_yandex_global_pixels(max_lon, min_lat, z)
        x0 = int(math.floor(min(px0, px1) / 256))
        x1 = int(math.floor(max(px0, px1) / 256))
        y0 = int(math.floor(min(py_ne, py_sw) / 256))
        y1 = int(math.floor(max(py_ne, py_sw) / 256))
        max_index = (2**z) - 1
        x0 = max(0, min(x0, max_index))
        x1 = max(0, min(x1, max_index))
        y0 = max(0, min(y0, max_index))
        y1 = max(0, min(y1, max_index))
        for x in range(x0, x1 + 1):
            for y in range(y0, y1 + 1):
                yield z, x, y


def _scheme_uins_for_tile_bbox(bbox: str, *, limit: int = 12) -> list[str]:
    minx, miny, maxx, maxy = bbox4326_to_3857(bbox)
    qs = InvestMnpScheme.objects.filter(status=InvestMnpScheme.Status.READY).filter(
        Q(extent_min_x__isnull=True)
        | (
            Q(extent_max_x__gte=minx)
            & Q(extent_min_x__lte=maxx)
            & Q(extent_max_y__gte=miny)
            & Q(extent_min_y__lte=maxy)
        )
    )
    uins = list(qs.values_list("uin", flat=True)[:limit])
    if uins:
        return uins
    # Fallback: all ready schemes (still KK-scoped in store)
    return list(
        InvestMnpScheme.objects.filter(status=InvestMnpScheme.Status.READY).values_list(
            "uin", flat=True
        )[:limit]
    )


def sync_tiles(
    *,
    zmin: int | None = None,
    zmax: int | None = None,
    bbox: str | None = None,
    around_sites: bool = False,
    buffer_deg: float | None = None,
    progress=None,
) -> dict[str, Any]:
    zmin = int(zmin if zmin is not None else getattr(settings, "INVEST_MNP_TILE_ZMIN", 8))
    zmax = int(zmax if zmax is not None else getattr(settings, "INVEST_MNP_TILE_ZMAX", 12))
    if zmin > zmax:
        zmin, zmax = zmax, zmin
    zmin = max(0, min(zmin, 18))
    zmax = max(0, min(zmax, 18))

    bboxes: list[str] = []
    if around_sites:
        bboxes = site_coverage_bboxes(buffer_deg=buffer_deg)
        if not bboxes:
            return {
                "tiles_planned": 0,
                "tiles_written": 0,
                "tiles_empty": 0,
                "tiles_error": 0,
                "bytes": 0,
                "zmin": zmin,
                "zmax": zmax,
                "around_sites": True,
                "note": "no sites with coordinates",
            }
    elif bbox:
        bboxes = [validate_bbox(bbox)]
    else:
        bboxes = [region_bbox()]

    tile_keys: set[tuple[int, int, int]] = set()
    for bb in bboxes:
        for key in iter_yandex_tiles_for_bbox(bb, zmin=zmin, zmax=zmax):
            tile_keys.add(key)
    tiles = sorted(tile_keys)
    stats = {
        "tiles_planned": len(tiles),
        "tiles_written": 0,
        "tiles_empty": 0,
        "tiles_error": 0,
        "bytes": 0,
        "zmin": zmin,
        "zmax": zmax,
        "bboxes": len(bboxes),
        "around_sites": bool(around_sites),
    }
    for idx, (z, x, y) in enumerate(tiles, start=1):
        tile_bbox = yandex_tile_bbox_4326(z, x, y)
        uins = _scheme_uins_for_tile_bbox(tile_bbox)
        cql = build_cql_for_uins(uins)
        if progress and (idx == 1 or idx % 25 == 0 or idx == len(tiles)):
            progress(f"tiles {idx}/{len(tiles)} z={z} x={x} y={y}")
        if not cql:
            write_tile_bytes(z, x, y, _TRANSPARENT_PNG)
            stats["tiles_empty"] += 1
            continue
        try:
            content, _ctype = fetch_mnp_wms_upstream(
                bbox=tile_bbox,
                width=256,
                height=256,
                srs="EPSG:4326",
                cql_filter=cql,
            )
            if not content or content[:4] != b"\x89PNG":
                content = _TRANSPARENT_PNG
                stats["tiles_empty"] += 1
            else:
                stats["tiles_written"] += 1
                stats["bytes"] += len(content)
            write_tile_bytes(z, x, y, content)
        except Exception:  # noqa: BLE001
            stats["tiles_error"] += 1
            logger.exception("MNP tile sync failed z=%s x=%s y=%s", z, x, y)
            write_tile_bytes(z, x, y, _TRANSPARENT_PNG)
    return stats


def site_coverage_bboxes(*, buffer_deg: float | None = None) -> list[str]:
    """Buffered lon/lat bboxes around InvestSite points (for high-z tile bake)."""
    from delayu.models_invest import InvestSite

    buf = float(
        buffer_deg
        if buffer_deg is not None
        else getattr(settings, "INVEST_MNP_SITE_TILE_BUFFER_DEG", 0.05)
    )
    buf = max(0.005, min(buf, 0.5))
    boxes: list[str] = []
    qs = (
        InvestSite.objects.exclude(latitude__isnull=True)
        .exclude(longitude__isnull=True)
        .values_list("longitude", "latitude")
    )
    for lon, lat in qs.iterator():
        try:
            lon_f = float(lon)
            lat_f = float(lat)
        except (TypeError, ValueError):
            continue
        boxes.append(
            validate_bbox(
                f"{lon_f - buf},{lat_f - buf},{lon_f + buf},{lat_f + buf}"
            )
        )
    return boxes


def run_sync(
    *,
    features: bool = True,
    tiles: bool = True,
    limit_schemes: int | None = None,
    zmin: int | None = None,
    zmax: int | None = None,
    around_sites: bool = False,
    buffer_deg: float | None = None,
    progress=None,
) -> InvestMnpSyncRun:
    run = InvestMnpSyncRun.objects.create(stats={"phase": "started"})
    stats: dict[str, Any] = {}
    try:
        if features:
            stats["features"] = sync_features(limit_schemes=limit_schemes, progress=progress)
        if tiles:
            stats["tiles"] = sync_tiles(
                zmin=zmin,
                zmax=zmax,
                around_sites=around_sites,
                buffer_deg=buffer_deg,
                progress=progress,
            )
        run.ok = True
        run.stats = stats
        run.error = ""
    except Exception as exc:  # noqa: BLE001
        logger.exception("MNP store sync failed")
        run.ok = False
        run.stats = stats
        run.error = str(exc)[:4000]
        raise
    finally:
        run.finished_at = timezone.now()
        run.save(update_fields=["ok", "stats", "error", "finished_at"])
    return run
