"""MNP local store + tile/feature endpoints."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.urls import reverse

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import InvestMnpFeature, InvestMnpScheme, InvestMnpSyncRun
from delayu.services.invest_mnp import (
    InvestMnpError,
    build_cql_for_uins,
    fetch_mnp_wfs,
    fetch_mnp_wms,
    fetch_mnp_wms_upstream,
    mnp_map_config,
    mercator_to_lonlat,
    validate_bbox,
)
from delayu.services.invest_mnp_store import (
    filter_kk_schemes,
    query_features_geojson,
    read_tile_bytes,
    store_status,
    write_tile_bytes,
    yandex_tile_bbox_4326,
)
from delayu.services.invest_roles import perm_for_role

User = get_user_model()

_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def mnp_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-mnp", name="MNP Map", industry_template="invest", status="active"
    )
    module = ModuleCatalog.objects.create(code="M22", name="Инвестпроекты")
    SubsystemModule.objects.create(subsystem=sub, module=module, enabled=True)
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    role = Role.objects.create(subsystem=sub, code="invest_agency", name="Агентство")
    RoleModulePermission.objects.create(role=role, module=module, **perm_for_role("invest_agency", "M22"))
    user = User.objects.create_user("mnp_user", password="x")
    SubsystemMembership.objects.create(
        user=user, subsystem=sub, organization=org, role=role, is_default=True
    )
    return {"sub": sub, "user": user}


def test_validate_bbox_ok():
    assert validate_bbox("38.9,45.0,39.2,45.1") == "38.9,45.0,39.2,45.1"


def test_validate_bbox_rejects_huge():
    with pytest.raises(InvestMnpError):
        validate_bbox("0,0,50,50")


def test_mnp_map_config_defaults(mnp_ctx):
    cfg = mnp_map_config(mnp_ctx["sub"])
    assert "mnp.economy.gov.ru" in cfg["wms_url"]
    assert "geo_db_data_fgistp_pol" in cfg["wms_layers"]
    assert cfg["enabled"] is True


def test_build_cql_for_uins():
    assert build_cql_for_uins(["0372000002020302202407251"]) == "uin='0372000002020302202407251'"


def test_mercator_roundtrip_approx():
    lon, lat = mercator_to_lonlat(4185000.0, 5589000.0)
    assert 37.0 < lon < 38.5
    assert 44.0 < lat < 45.5


def test_filter_kk_schemes_only_03_and_extent():
    rows = [
        {
            "uin": "0372000002020302202407251",
            "stp_name": "Новороссийск",
            "stp_extent": "4166063.76_5566487.24_4221440.02_5623365.15",
        },
        {
            "uin": "5263041302020304202411131",
            "stp_name": "Другой субъект",
            "stp_extent": "4166063.76_5566487.24_4221440.02_5623365.15",
        },
        {
            "uin": "03000000020102202301241",
            "stp_name": "КК огромный",
            "stp_extent": "1000000_1000000_9000000_9000000",
        },
    ]
    hits = filter_kk_schemes(rows)
    assert [h["uin"] for h in hits] == ["0372000002020302202407251"]


def test_yandex_tile_bbox_reasonable():
    bbox = yandex_tile_bbox_4326(10, 615, 321)
    parts = [float(p) for p in bbox.split(",")]
    assert parts[0] < parts[2]
    assert parts[1] < parts[3]


@patch("delayu.services.invest_mnp.schemes_intersecting_bbox")
@patch("delayu.services.invest_mnp.httpx.Client")
def test_fetch_mnp_wms_upstream_ok(mock_client_cls, mock_schemes):
    mock_schemes.return_value = [{"uin": "0372000002020302202407251", "stp_name": "Генплан"}]
    mock_client = MagicMock()
    mock_client_cls.return_value.__enter__.return_value = mock_client
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "image/png"}
    mock_resp.content = b"\x89PNG\r\n"
    mock_client.get.return_value = mock_resp

    content, ctype = fetch_mnp_wms_upstream(bbox="37.8,44.5,38.2,44.9", width=256, height=256)
    assert content.startswith(b"\x89PNG")
    assert ctype == "image/png"
    params = mock_client.get.call_args.kwargs.get("params") or mock_client.get.call_args[1].get("params")
    assert "CQL_FILTER" in params


def test_fetch_mnp_wms_runtime_no_upstream():
    content, ctype = fetch_mnp_wms(bbox="37.8,44.5,38.2,44.9")
    assert ctype == "image/png"
    assert content[:4] == b"\x89PNG"


@pytest.mark.django_db
def test_query_features_bbox(mnp_ctx):
    scheme = InvestMnpScheme.objects.create(
        uin="0372000002020302202407251",
        name="Генплан",
        status=InvestMnpScheme.Status.READY,
        feature_count=1,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="f1",
        classid="701010101",
        class_name="Жилая",
        geom_type="100",
        properties={"name": "Зона А"},
        geometry={
            "type": "Polygon",
            "coordinates": [[[37.7, 44.7], [37.71, 44.7], [37.71, 44.71], [37.7, 44.7]]],
        },
        bbox_min_lon=37.7,
        bbox_min_lat=44.7,
        bbox_max_lon=37.71,
        bbox_max_lat=44.71,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="f2",
        classid="701010101",
        properties={"name": "Далеко"},
        geometry={"type": "Polygon", "coordinates": [[[40.0, 46.0], [40.1, 46.0], [40.1, 46.1], [40.0, 46.0]]]},
        bbox_min_lon=40.0,
        bbox_min_lat=46.0,
        bbox_max_lon=40.1,
        bbox_max_lat=46.1,
    )
    # Distant scheme created first (lower id) but must not steal slots for local bbox.
    other = InvestMnpScheme.objects.create(
        uin="0360000000000000000000001",
        name="Чужая",
        status=InvestMnpScheme.Status.READY,
        extent_min_x=1_000_000,
        extent_min_y=1_000_000,
        extent_max_x=2_000_000,
        extent_max_y=2_000_000,
        feature_count=1,
    )
    InvestMnpFeature.objects.create(
        scheme=other,
        external_id="far",
        classid="701010101",
        properties={"name": "Чужая зона"},
        geometry={
            "type": "Polygon",
            "coordinates": [[[10.0, 50.0], [10.1, 50.0], [10.1, 50.1], [10.0, 50.0]]],
        },
        bbox_min_lon=10.0,
        bbox_min_lat=50.0,
        bbox_max_lon=10.1,
        bbox_max_lat=50.1,
    )
    # Local scheme extents around Novorossiysk (EPSG:3857 approx).
    scheme.extent_min_x = 4166063.76
    scheme.extent_min_y = 5566487.24
    scheme.extent_max_x = 4221440.02
    scheme.extent_max_y = 5623365.15
    scheme.save(update_fields=["extent_min_x", "extent_min_y", "extent_max_x", "extent_max_y"])

    data = query_features_geojson(bbox="37.69,44.69,37.72,44.72", max_features=10)
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["name"] == "Зона А"
    assert data["meta"]["schemes"] == ["0372000002020302202407251"]

    via_wfs = fetch_mnp_wfs(bbox="37.69,44.69,37.72,44.72", max_features=10)
    assert len(via_wfs["features"]) == 1


@pytest.mark.django_db
def test_tile_read_write(tmp_path, settings, mnp_ctx):
    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    write_tile_bytes(10, 1, 2, _TINY_PNG + b"extra")
    assert read_tile_bytes(10, 1, 2).startswith(b"\x89PNG")
    missing = read_tile_bytes(10, 9, 9)
    assert missing[:4] == b"\x89PNG"


@pytest.mark.django_db
def test_tile_overzoom_from_parent(tmp_path, settings, mnp_ctx):
    from PIL import Image
    import io

    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    settings.INVEST_MNP_TILE_ZMIN = 8
    # Parent z=10 tile with distinct color blocks.
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    for qx, qy, color in [
        (0, 0, (255, 0, 0, 255)),
        (1, 0, (0, 255, 0, 255)),
        (0, 1, (0, 0, 255, 255)),
        (1, 1, (255, 255, 0, 255)),
    ]:
        for dx in range(128):
            for dy in range(128):
                img.putpixel((qx * 128 + dx, qy * 128 + dy), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    write_tile_bytes(10, 4, 6, buf.getvalue())

    # Child of (10,4,6) at z=11 in bottom-right quadrant -> (11,9,13)
    child = read_tile_bytes(11, 9, 13)
    assert child[:4] == b"\x89PNG"
    out = Image.open(io.BytesIO(child)).convert("RGBA")
    # Center pixel should be yellow-ish from BR quadrant
    pixel = out.getpixel((128, 128))
    assert pixel[0] > 200 and pixel[1] > 200 and pixel[2] < 50


@pytest.mark.django_db
@patch("delayu.services.invest_mnp_store.fetch_mnp_wms_upstream")
@patch("delayu.services.invest_mnp_store._fetch_stp_features")
@patch("delayu.services.invest_mnp_store._pick_vector_classid")
@patch("delayu.services.invest_mnp_store._fetch_layer_list")
@patch("delayu.services.invest_mnp_store.fetch_stp_list")
def test_sync_command_mocked(
    mock_stp,
    mock_layers,
    mock_pick,
    mock_feats,
    mock_wms,
    tmp_path,
    settings,
    mnp_ctx,
):
    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    settings.INVEST_MNP_TILE_ZMIN = 10
    settings.INVEST_MNP_TILE_ZMAX = 10
    # Tiny bbox → few tiles
    settings.INVEST_MNP_REGION_BBOX = "37.75,44.70,37.76,44.71"
    mock_stp.return_value = [
        {
            "uin": "0372000002020302202407251",
            "stp_name": "Новороссийск",
            "stp_extent": "4166063.76_5566487.24_4221440.02_5623365.15",
        }
    ]
    mock_layers.return_value = [
        {"classid": "701010101", "class_name": "Жилая", "geom_type": "100"}
    ]
    mock_pick.return_value = ("701010101", "100")
    mock_feats.return_value = [
        {
            "type": "Feature",
            "id": "1",
            "naim": "Зона",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [4185000.0, 5589000.0],
                        [4185100.0, 5589000.0],
                        [4185100.0, 5589100.0],
                        [4185000.0, 5589000.0],
                    ]
                ],
            },
        }
    ]
    mock_wms.return_value = (_TINY_PNG, "image/png")

    call_command("sync_mnp_kk", "--limit-schemes=1")
    assert InvestMnpScheme.objects.filter(uin="0372000002020302202407251").exists()
    assert InvestMnpFeature.objects.count() == 1
    assert InvestMnpSyncRun.objects.filter(ok=True).exists()
    assert store_status()["features"] == 1
    assert any(Path(settings.INVEST_MNP_STORE_DIR).joinpath("tiles").rglob("*.png"))


@pytest.mark.django_db
def test_tile_and_features_views(client, mnp_ctx, tmp_path, settings):
    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    write_tile_bytes(8, 3, 4, _TINY_PNG)
    scheme = InvestMnpScheme.objects.create(
        uin="0372test",
        name="T",
        status=InvestMnpScheme.Status.READY,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="e1",
        classid="701010101",
        properties={"name": "X"},
        geometry={
            "type": "Polygon",
            "coordinates": [[[37.7, 44.7], [37.71, 44.7], [37.71, 44.71], [37.7, 44.7]]],
        },
        bbox_min_lon=37.7,
        bbox_min_lat=44.7,
        bbox_max_lon=37.71,
        bbox_max_lat=44.71,
    )
    client.force_login(mnp_ctx["user"])
    tile = client.get(reverse("invest-mnp-tile", kwargs={"z": 8, "x": 3, "y": 4}))
    assert tile.status_code == 200
    assert tile["Content-Type"].startswith("image/png")
    feats = client.get(
        reverse("invest-mnp-features"),
        {"bbox": "37.69,44.69,37.72,44.72"},
    )
    assert feats.status_code == 200
    assert feats.json()["features"][0]["properties"]["name"] == "X"


@pytest.mark.django_db
@patch("delayu.views_invest.render_viewport_png")
def test_wms_proxy_view(mock_render, client, mnp_ctx):
    mock_render.return_value = b"\x89PNG"
    client.force_login(mnp_ctx["user"])
    response = client.get(
        reverse("invest-mnp-wms"),
        {"bbox": "38.9,45.0,39.2,45.1", "width": "256", "height": "256"},
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("image/png")


@pytest.mark.django_db
@patch("delayu.views_invest.render_viewport_png")
def test_viewport_view(mock_render, client, mnp_ctx):
    mock_render.return_value = b"\x89PNG\r\nviewport"
    client.force_login(mnp_ctx["user"])
    response = client.get(
        reverse("invest-mnp-viewport"),
        {"bbox": "37.7,44.7,37.8,44.75", "width": "800", "height": "480"},
    )
    assert response.status_code == 200
    assert response["Content-Type"].startswith("image/png")
    mock_render.assert_called_once()


@pytest.mark.django_db
def test_sites_map_exposes_local_store_ui(client, mnp_ctx):
    from decimal import Decimal

    from delayu.models_invest import InvestSite

    InvestSite.objects.create(
        subsystem=mnp_ctx["sub"],
        organization=Organization.objects.get(subsystem=mnp_ctx["sub"]),
        cadastral_number="23:43:0107001:101",
        name="Тест",
        latitude=Decimal("45.03"),
        longitude=Decimal("39.06"),
        completeness_pct=80,
    )
    client.force_login(mnp_ctx["user"])
    response = client.get(reverse("invest-sites-map"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Растр" in html
    assert "Вектор зон" in html
    assert "Авто (гибрид)" in html
    assert "map-annotation" in html
    assert "openBalloonOnClick: false" in html
    assert "showMnpAnnotation" in html
    assert "InvestBalloonLayout" in html or "invest-map-balloon" in html
    assert "balloonHtml" in html or "siteBalloonHtml" in html
    assert "islands#darkBlueStretchyIcon" not in html
    assert "viewportProxy" in html or "mnp-viewport" in html or "tileUrlTemplate" in html
    assert "vectorZoom" in html
    assert "sync_mnp_kk" in html or "тайлов" in html
    assert "fillImageHref" in html or "loadRaster" in html
    assert "Открыть в МНП" in html


def test_style_for_classid_known():
    from delayu.services.invest_mnp_styles import legend_items, style_for_classid

    st = style_for_classid("701010101")
    assert st["label"] == "Жилая"
    assert st["fill"].startswith("#")
    assert len(legend_items()) >= 5


@pytest.mark.django_db
def test_render_features_png_draws(mnp_ctx):
    from delayu.services.invest_mnp_store import render_features_png

    scheme = InvestMnpScheme.objects.create(
        uin="0372000002020302202407251",
        name="Генплан",
        status=InvestMnpScheme.Status.READY,
        extent_min_x=4166063.76,
        extent_min_y=5566487.24,
        extent_max_x=4221440.02,
        extent_max_y=5623365.15,
        feature_count=1,
    )
    InvestMnpFeature.objects.create(
        scheme=scheme,
        external_id="f1",
        classid="701010101",
        class_name="Жилая",
        geom_type="100",
        properties={"name": "Зона А", "classid": "701010101"},
        geometry={
            "type": "Polygon",
            "coordinates": [[[37.7, 44.7], [37.71, 44.7], [37.71, 44.71], [37.7, 44.7]]],
        },
        bbox_min_lon=37.7,
        bbox_min_lat=44.7,
        bbox_max_lon=37.71,
        bbox_max_lat=44.71,
    )
    png = render_features_png(bbox="37.69,44.69,37.72,44.72", width=256, height=256)
    assert png[:4] == b"\x89PNG"
    assert len(png) > 500


@pytest.mark.django_db
def test_site_coverage_bboxes(mnp_ctx, settings):
    from decimal import Decimal

    from delayu.models_invest import InvestSite
    from delayu.services.invest_mnp_store import site_coverage_bboxes

    settings.INVEST_MNP_SITE_TILE_BUFFER_DEG = 0.02
    InvestSite.objects.create(
        subsystem=mnp_ctx["sub"],
        organization=Organization.objects.get(subsystem=mnp_ctx["sub"]),
        cadastral_number="23:43:0107001:102",
        name="Точка",
        latitude=Decimal("44.72"),
        longitude=Decimal("37.77"),
        completeness_pct=50,
    )
    boxes = site_coverage_bboxes()
    assert len(boxes) >= 1
    parts = [float(p) for p in boxes[0].split(",")]
    assert parts[0] < 37.77 < parts[2]
    assert parts[1] < 44.72 < parts[3]


@pytest.mark.django_db
@patch("delayu.services.invest_mnp_store.fetch_mnp_wms_upstream")
def test_viewport_disk_cache_hit(mock_wms, mnp_ctx, settings, tmp_path):
    from PIL import Image
    import io

    from delayu.services import invest_mnp_store as store

    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    settings.INVEST_MNP_LIVE_WMS = True
    settings.INVEST_MNP_LIVE_WMS_CACHE = False
    settings.INVEST_MNP_VIEWPORT_CACHE_TTL = 3600
    InvestMnpScheme.objects.update_or_create(
        uin="0372viewportcache0000000001",
        defaults={
            "name": "Cache",
            "status": InvestMnpScheme.Status.READY,
            "extent_min_x": 4166063.76,
            "extent_min_y": 5566487.24,
            "extent_max_x": 4221440.02,
            "extent_max_y": 5623365.15,
        },
    )
    img = Image.new("RGBA", (256, 256), (0, 128, 255, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    payload = buf.getvalue()
    mock_wms.return_value = (payload, "image/png")

    kwargs = dict(
        bbox="37.7412,44.7011,37.8019,44.7418",
        width=128,
        height=128,
        mode="detail",
        zoom=14,
        allow_live=True,
    )
    first = store.render_viewport_png(**kwargs)
    assert first[:4] == b"\x89PNG"
    assert mock_wms.call_count >= 1
    cached_files = list(store.viewport_cache_root().glob("*.png"))
    assert cached_files, f"store={store.store_root()} len(first)={len(first)}"

    # Tiny pan within same 3dp quantized cell at z=14
    second = store.render_viewport_png(
        bbox="37.74125,44.70115,37.80195,44.74185",
        width=128,
        height=128,
        mode="detail",
        zoom=14,
        allow_live=True,
    )
    assert second == first
    assert mock_wms.call_count == 1


@pytest.mark.django_db
@patch("delayu.services.invest_mnp_store.fetch_mnp_wms_upstream")
def test_detail_mode_prefers_live_wms(mock_wms, mnp_ctx, settings, tmp_path):
    from PIL import Image
    import io

    from delayu.services.invest_mnp_store import render_viewport_png

    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    settings.INVEST_MNP_LIVE_WMS = True
    settings.INVEST_MNP_LIVE_WMS_CACHE = False
    InvestMnpScheme.objects.update_or_create(
        uin="0372detailmode0000000000001",
        defaults={
            "name": "Генплан detail",
            "status": InvestMnpScheme.Status.READY,
            "extent_min_x": 4166063.76,
            "extent_min_y": 5566487.24,
            "extent_max_x": 4221440.02,
            "extent_max_y": 5623365.15,
        },
    )
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    mock_wms.return_value = (buf.getvalue(), "image/png")
    png = render_viewport_png(
        bbox="37.74,44.70,37.80,44.74",
        width=128,
        height=128,
        mode="detail",
        zoom=14,
        allow_live=True,
    )
    assert png[:4] == b"\x89PNG"
    mock_wms.assert_called()


@pytest.mark.django_db
@patch("delayu.services.invest_mnp_store.fetch_mnp_wms_upstream")
def test_live_wms_on_empty_local(mock_wms, mnp_ctx, settings, tmp_path):
    from delayu.services.invest_mnp_store import render_viewport_png

    settings.INVEST_MNP_STORE_DIR = str(tmp_path / "mnp")
    settings.INVEST_MNP_LIVE_WMS = True
    settings.INVEST_MNP_LIVE_WMS_CACHE = False
    InvestMnpScheme.objects.update_or_create(
        uin="0372livemiss000000000000001",
        defaults={
            "name": "Генплан",
            "status": InvestMnpScheme.Status.READY,
            "extent_min_x": 4166063.76,
            "extent_min_y": 5566487.24,
            "extent_max_x": 4221440.02,
            "extent_max_y": 5623365.15,
        },
    )
    mock_wms.return_value = (_TINY_PNG + b"live", "image/png")
    png = render_viewport_png(
        bbox="37.74,44.70,37.80,44.74",
        width=128,
        height=128,
        mode="tiles",
        zoom=10,
        allow_live=True,
    )
    assert png.startswith(b"\x89PNG")
    mock_wms.assert_called()
