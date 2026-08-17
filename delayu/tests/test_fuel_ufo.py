# -*- coding: utf-8 -*-
from django.test import Client, TestCase
from django.utils import timezone

from delayu.models_fuel_ufo import (
    FuelUfoAvailability,
    FuelUfoAzsPoint,
    FuelUfoDataSource,
    FuelUfoRegion,
)
from delayu.models_fuel_ufo import point_in_ufo
from delayu.services import fuel_ufo as svc
from delayu.data.fuel_ufo_azs import SEED_AZS


class FuelUfoGeoTests(TestCase):
    def test_novorossiysk_in_ufo(self):
        self.assertTrue(point_in_ufo(44.72, 37.77))

    def test_moscow_out_of_ufo(self):
        self.assertFalse(point_in_ufo(55.75, 37.62))


class FuelUfoCatalogTests(TestCase):
    def test_catalog_covers_ufo(self):
        self.assertGreaterEqual(len(SEED_AZS), 1000)
        regions = {row[4] for row in SEED_AZS}
        self.assertGreaterEqual(len(regions), 8)
        cities = {row[5] for row in SEED_AZS}
        self.assertGreaterEqual(len(cities), 80)


class FuelUfoApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.azs = FuelUfoAzsPoint.objects.create(
            code="test-nvr-1",
            name="Тест АЗС",
            network="Тест",
            address="Новороссийск",
            region=FuelUfoRegion.KRASNODAR,
            city="Новороссийск",
            latitude=44.7238,
            longitude=37.7689,
        )
        svc.ingest_partner_mock(
            self.azs, FuelUfoDataSource.SBER, "ai95", FuelUfoAvailability.OK
        )

    def test_meta(self):
        r = self.client.get("/fuel/api/ufo/meta/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["scope"], "ufo")
        self.assertTrue(len(data["regions"]) >= 8)
        self.assertIn("networks", data)

    def test_list_network_filter(self):
        self.azs.network = "Лукойл"
        self.azs.save(update_fields=["network"])
        r = self.client.get("/fuel/api/ufo/azs/", {"network": "Лукойл"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(data["count"], 1)
        for item in data["results"]:
            self.assertEqual(item["network"], "Лукойл")

    def test_list(self):
        r = self.client.get("/fuel/api/ufo/azs/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertGreaterEqual(data["count"], 1)
        item = data["results"][0]
        self.assertIn("last_reliable_at", item)
        self.assertIn("sources", item)
        self.assertIn("freshness_label", item)
        self.assertIn("status_labels", item)
        self.assertEqual(item["status_labels"]["ai95"], "Есть")
        self.assertIn("sources", item)
        self.assertIn("status_label", item["sources"].get("ai95") or {"status_label": "Есть"})

    def test_list_grade_available(self):
        r = self.client.get("/fuel/api/ufo/azs/", {"grade": "ai95", "available": "1"})
        self.assertEqual(r.status_code, 200)
        for item in r.json()["results"]:
            self.assertIn(item["status"]["ai95"], ("ok", "low"))

    def test_route_stays_in_app(self):
        r = self.client.get(
            "/fuel/api/ufo/route/",
            {
                "from_lat": "44.72",
                "from_lon": "37.77",
                "azs_id": str(self.azs.id),
            },
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertIn(data["engine"], ("yandex", "osrm", "estimate"))
        self.assertGreater(data["distance_m"], 0)
        self.assertIn("duration_text", data)
        if data["engine"] != "estimate":
            self.assertGreater(len(data["polyline"]), 2)

    def test_search_q(self):
        r = self.client.get("/fuel/api/ufo/azs/", {"q": "Новороссийск"})
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(r.json()["count"], 1)

    def test_report(self):
        start = self.client.post(
            "/fuel/api/ufo/auth/start/",
            data={"phone": "+7 918 000-00-01", "full_name": "Иван Тестов", "agree_pd": True},
            content_type="application/json",
        )
        code = start.json()["demo_code"]
        self.client.post(
            "/fuel/api/ufo/auth/verify/",
            data={"phone": "+7 918 000-00-01", "code": code},
            content_type="application/json",
        )
        r = self.client.post(
            "/fuel/api/ufo/reports/",
            data={
                "azs_id": self.azs.id,
                "device_id": "testdevice123456",
                "availability": "low",
                "fuel_grade": "ai95",
                "queue_minutes": 40,
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 201)
        self.azs.refresh_from_db()
        snap = self.azs.snapshot
        self.assertIsNotNone(snap)
        again = self.client.post(
            "/fuel/api/ufo/reports/",
            data={
                "azs_id": self.azs.id,
                "device_id": "testdevice123456",
                "availability": "ok",
                "fuel_grade": "ai95",
            },
            content_type="application/json",
        )
        self.assertEqual(again.status_code, 429)
        self.assertEqual(again.json()["error"], "already_today")

    def test_report_requires_login(self):
        r = self.client.post(
            "/fuel/api/ufo/reports/",
            data={
                "azs_id": self.azs.id,
                "device_id": "testdevice123456",
                "availability": "ok",
                "fuel_grade": "ai95",
            },
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    def test_geo_check(self):
        r = self.client.get("/fuel/api/ufo/geo-check/", {"lat": "44.72", "lon": "37.77"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["in_ufo"])

    def test_status(self):
        r = self.client.get("/fuel/api/ufo/status/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["online"])

    def test_auth_otp(self):
        r = self.client.post(
            "/fuel/api/ufo/auth/start/",
            data={"phone": "+7 918 000-00-01", "full_name": "Иван Тестов", "agree_pd": True},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        code = r.json().get("demo_code")
        self.assertTrue(code)
        v = self.client.post(
            "/fuel/api/ufo/auth/verify/",
            data={"phone": "+7 918 000-00-01", "code": code},
            content_type="application/json",
        )
        self.assertEqual(v.status_code, 200)
        me = self.client.get("/fuel/api/ufo/auth/me/")
        self.assertTrue(me.json()["ok"])
        self.assertEqual(me.json()["user"]["name"], "Иван Тестов")


class FuelUfoLegalPagesTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_privacy_page(self):
        r = self.client.get("/fuel/ufo/legal/privacy/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "персональных данных")
        self.assertNotContains(r, "solely")

    def test_rules_page(self):
        r = self.client.get("/fuel/ufo/legal/rules/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Правила сервиса")

    def test_support_page(self):
        r = self.client.get("/fuel/ufo/support/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Техподдержка")

    def test_android_install_page(self):
        r = self.client.get("/fuel/ufo/android/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Скачать APK")
        self.assertContains(r, "/fuel/ufo/android/fuel-ufo.apk")

    def test_apk_download(self):
        r = self.client.get("/fuel/ufo/android/fuel-ufo.apk")
        self.assertEqual(r.status_code, 200)
        self.assertIn("android.package-archive", r["Content-Type"])
        self.assertGreater(int(r.get("Content-Length") or 0), 1000)

    def test_app_links_to_ufo_legal(self):
        r = self.client.get("/fuel/ufo/app/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "/fuel/ufo/legal/privacy/")
        self.assertContains(r, "/fuel/ufo/legal/rules/")
        self.assertContains(r, "network-filters")
        self.assertContains(r, "Еду сюда")
        self.assertNotContains(r, "/fuel/novorossiysk/")
        self.assertNotContains(r, "портале жителя")
