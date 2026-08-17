# -*- coding: utf-8 -*-
from django.contrib import admin

from delayu.models_fuel_ufo import (
    FuelUfoAzsPoint,
    FuelUfoRegionBanner,
    FuelUfoSnapshot,
    FuelUfoSourceObservation,
    FuelUfoUserReport,
)


@admin.register(FuelUfoAzsPoint)
class FuelUfoAzsPointAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "city", "region", "network", "is_active")
    list_filter = ("region", "is_active", "network")
    search_fields = ("code", "name", "address", "city")


@admin.register(FuelUfoSnapshot)
class FuelUfoSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "azs",
        "status_ai95",
        "status_ai92",
        "status_diesel",
        "primary_source",
        "last_reliable_at",
    )
    list_filter = ("primary_source", "status_ai95")


@admin.register(FuelUfoSourceObservation)
class FuelUfoSourceObservationAdmin(admin.ModelAdmin):
    list_display = ("azs", "source", "fuel_grade", "availability", "observed_at")
    list_filter = ("source", "fuel_grade", "availability")


@admin.register(FuelUfoUserReport)
class FuelUfoUserReportAdmin(admin.ModelAdmin):
    list_display = ("azs", "device_id", "availability", "fuel_grade", "created_at", "is_rejected")
    list_filter = ("availability", "is_rejected")


@admin.register(FuelUfoRegionBanner)
class FuelUfoRegionBannerAdmin(admin.ModelAdmin):
    list_display = ("region", "title", "is_active", "updated_at")
