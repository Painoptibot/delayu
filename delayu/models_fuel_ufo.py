# -*- coding: utf-8 -*-
"""Агрегация статусов АЗС по ЮФО для мобильного приложения."""
from __future__ import annotations

from django.db import models
from django.utils import timezone


class FuelUfoRegion(models.TextChoices):
    ADYGEA = "adygea", "Республика Адыгея"
    KALMYKIA = "kalmykia", "Республика Калмыкия"
    CRIMEA = "crimea", "Республика Крым"
    SEVASTOPOL = "sevastopol", "г. Севастополь"
    KRASNODAR = "krasnodar", "Краснодарский край"
    ASTRAKHAN = "astrakhan", "Астраханская область"
    VOLGOGRAD = "volgograd", "Волгоградская область"
    ROSTOV = "rostov", "Ростовская область"


# Приблизительные bbox субъектов ЮФО (min_lat, min_lon, max_lat, max_lon)
UFO_REGION_BBOX: dict[str, tuple[float, float, float, float]] = {
    FuelUfoRegion.ADYGEA: (43.85, 38.95, 45.25, 40.85),
    FuelUfoRegion.KALMYKIA: (44.70, 43.80, 48.50, 47.60),
    FuelUfoRegion.CRIMEA: (44.20, 32.30, 46.30, 36.80),
    FuelUfoRegion.SEVASTOPOL: (44.35, 33.30, 44.85, 33.95),
    FuelUfoRegion.KRASNODAR: (43.30, 36.50, 47.00, 41.80),
    FuelUfoRegion.ASTRAKHAN: (45.40, 45.80, 48.90, 49.20),
    FuelUfoRegion.VOLGOGRAD: (47.40, 41.10, 51.30, 47.40),
    FuelUfoRegion.ROSTOV: (45.80, 38.20, 50.20, 44.30),
}

# Общий bbox ЮФО
UFO_BBOX = (43.0, 32.0, 51.5, 49.5)


class FuelUfoDataSource(models.TextChoices):
    SBER = "sber", "Сбер (партнёр / mock)"
    TBANK = "tbank", "Т‑Банк (партнёр / mock)"
    USER = "user", "Пользователи"
    AZS_OPERATOR = "azs_operator", "Оператор АЗС"
    CITY_HQ = "city_hq", "Штаб города"
    YANDEX_TRAFFIC = "yandex_traffic", "Яндекс.Пробки"
    MANUAL = "manual", "Ручной ввод"


class FuelUfoAvailability(models.TextChoices):
    OK = "ok", "Есть"
    LOW = "low", "Мало"
    EMPTY = "empty", "Нет"
    UNKNOWN = "unknown", "Неизвестно"


class FuelUfoAzsPoint(models.Model):
    """Точка АЗС в контуре ЮФО (общий справочник для мобильного приложения)."""

    code = models.CharField("Код", max_length=64, unique=True)
    name = models.CharField("Название", max_length=255)
    network = models.CharField("Сеть", max_length=128, blank=True, default="")
    address = models.CharField("Адрес", max_length=512)
    region = models.CharField(
        "Субъект ЮФО", max_length=32, choices=FuelUfoRegion.choices, db_index=True
    )
    city = models.CharField("Город", max_length=128, blank=True, default="")
    latitude = models.DecimalField("Широта", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("Долгота", max_digits=9, decimal_places=6)
    external_sber_id = models.CharField(max_length=64, blank=True, default="")
    external_tbank_id = models.CharField(max_length=64, blank=True, default="")
    fuel_azs_station = models.ForeignKey(
        "FuelAzsStation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ufo_points",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "АЗС ЮФО"
        verbose_name_plural = "АЗС ЮФО"
        ordering = ["region", "city", "name"]
        indexes = [
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city or self.region})"


class FuelUfoSourceObservation(models.Model):
    """Сырое наблюдение от источника."""

    azs = models.ForeignKey(
        FuelUfoAzsPoint, on_delete=models.CASCADE, related_name="observations"
    )
    source = models.CharField(max_length=32, choices=FuelUfoDataSource.choices, db_index=True)
    fuel_grade = models.CharField(
        "Марка", max_length=16, default="ai95"
    )  # ai92/ai95/diesel/gas
    availability = models.CharField(
        max_length=16, choices=FuelUfoAvailability.choices, default=FuelUfoAvailability.UNKNOWN
    )
    queue_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    limit_liters = models.PositiveSmallIntegerField(null=True, blank=True)
    cans_allowed = models.BooleanField(null=True, blank=True)
    confidence = models.FloatField(default=0.5)
    observed_at = models.DateTimeField(db_index=True)
    ingested_at = models.DateTimeField(auto_now_add=True)
    raw_note = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        verbose_name = "Наблюдение ЮФО"
        verbose_name_plural = "Наблюдения ЮФО"
        ordering = ["-observed_at"]
        indexes = [
            models.Index(fields=["azs", "source", "-observed_at"]),
        ]


class FuelUfoSnapshot(models.Model):
    """Агрегированный статус АЗС для API."""

    azs = models.OneToOneField(
        FuelUfoAzsPoint, on_delete=models.CASCADE, related_name="snapshot"
    )
    status_ai92 = models.CharField(
        max_length=16, choices=FuelUfoAvailability.choices, default=FuelUfoAvailability.UNKNOWN
    )
    status_ai95 = models.CharField(
        max_length=16, choices=FuelUfoAvailability.choices, default=FuelUfoAvailability.UNKNOWN
    )
    status_diesel = models.CharField(
        max_length=16, choices=FuelUfoAvailability.choices, default=FuelUfoAvailability.UNKNOWN
    )
    primary_source = models.CharField(
        max_length=32, choices=FuelUfoDataSource.choices, blank=True, default=""
    )
    confidence = models.FloatField(default=0.0)
    last_reliable_at = models.DateTimeField(null=True, blank=True)
    queue_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    traffic_jams = models.PositiveSmallIntegerField(
        "Пробки 0–10", null=True, blank=True
    )
    traffic_fetched_at = models.DateTimeField(null=True, blank=True)
    sources_json = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Снимок статуса ЮФО"
        verbose_name_plural = "Снимки статусов ЮФО"


class FuelUfoUserReport(models.Model):
    """Сообщение пользователя о ситуации на АЗС."""

    azs = models.ForeignKey(
        FuelUfoAzsPoint, on_delete=models.CASCADE, related_name="user_reports"
    )
    device_id = models.CharField(max_length=64, db_index=True)
    availability = models.CharField(
        max_length=16, choices=FuelUfoAvailability.choices, default=FuelUfoAvailability.UNKNOWN
    )
    fuel_grade = models.CharField(max_length=16, default="ai95")
    queue_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    limit_liters = models.PositiveSmallIntegerField(null=True, blank=True)
    cans_allowed = models.BooleanField(null=True, blank=True)
    comment = models.CharField(max_length=500, blank=True, default="")
    is_rejected = models.BooleanField(default=False)
    phone = models.CharField(max_length=16, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Репорт пользователя ЮФО"
        verbose_name_plural = "Репорты пользователей ЮФО"
        ordering = ["-created_at"]


class FuelUfoRegionBanner(models.Model):
    """Баннер лимитов / волны по субъекту ЮФО."""

    region = models.CharField(max_length=32, choices=FuelUfoRegion.choices, unique=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Баннер региона ЮФО"
        verbose_name_plural = "Баннеры регионов ЮФО"

    def __str__(self) -> str:
        return f"{self.get_region_display()}: {self.title}"


def point_in_ufo(lat: float, lon: float) -> bool:
    min_lat, min_lon, max_lat, max_lon = UFO_BBOX
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def detect_ufo_region(lat: float, lon: float) -> str | None:
    if not point_in_ufo(lat, lon):
        return None
    for code, (a, b, c, d) in UFO_REGION_BBOX.items():
        if a <= lat <= c and b <= lon <= d:
            return code
    return FuelUfoRegion.KRASNODAR  # fallback inside UFO bbox
