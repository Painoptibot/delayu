"""URL публичного портала «Топливный пропуск» (граждане + АЗС)."""
from django.urls import include, path

from delayu import views_fuel_azs as azs_views
from delayu import views_fuel_public as views

fuel_urlpatterns = [
    path("", views.FuelCitizenHomeView.as_view(), name="fuel-citizen-home"),
    path("login/", views.FuelCitizenLoginView.as_view(), name="fuel-citizen-login"),
    path("login/verify/", views.FuelCitizenLoginVerifyView.as_view(), name="fuel-citizen-login-verify"),
    path("logout/", views.FuelCitizenLogoutView.as_view(), name="fuel-citizen-logout"),
    path("auth/esia/<int:pk>/start/", views.FuelEsiaStartView.as_view(), name="fuel-esia-start"),
    path("auth/esia/callback/", views.FuelEsiaCallbackView.as_view(), name="fuel-esia-callback"),
    path("manifest.webmanifest", views.FuelManifestView.as_view(), name="fuel-manifest"),
    path("apply/", views.FuelApplicationCreateView.as_view(), name="fuel-application-create"),
    path("applications/", views.FuelApplicationListView.as_view(), name="fuel-application-list"),
    path(
        "applications/<int:pk>/",
        views.FuelApplicationDetailView.as_view(),
        name="fuel-application-detail",
    ),
    path("permits/<int:pk>/", views.FuelPermitQrView.as_view(), name="fuel-permit-qr"),
    path(
        "permits/<int:pk>/qr.svg",
        views.FuelPermitQrSvgView.as_view(),
        name="fuel-permit-qr-svg",
    ),
    path("map/", views.FuelMapView.as_view(), name="fuel-map"),
    path("history/", views.FuelHistoryView.as_view(), name="fuel-history"),
    path("profile/", views.FuelProfileView.as_view(), name="fuel-profile"),
    path("support/", views.FuelSupportView.as_view(), name="fuel-support"),
    path("legal/privacy/", views.FuelLegalPrivacyView.as_view(), name="fuel-legal-privacy"),
    path("legal/rules/", views.FuelLegalRulesView.as_view(), name="fuel-legal-rules"),
    path("sw.js", views.FuelCitizenServiceWorkerView.as_view(), name="fuel-citizen-sw"),
    path("api/status/", views.FuelPortalStatusApiView.as_view(), name="fuel-api-status"),
    path(
        "api/applications/sync/",
        views.FuelApplicationSyncApiView.as_view(),
        name="fuel-api-apply-sync",
    ),
    path("api/party/", views.FuelPartySuggestView.as_view(), name="fuel-api-party"),
    path("api/vehicles/", views.FuelVehicleSuggestView.as_view(), name="fuel-api-vehicles"),
    # АЗС
    path("azs/", azs_views.FuelAzsScanView.as_view(), name="fuel-azs-scan"),
    path("azs/login/", azs_views.FuelAzsLoginView.as_view(), name="fuel-azs-login"),
    path("azs/logout/", azs_views.FuelAzsLogoutView.as_view(), name="fuel-azs-logout"),
    path("azs/confirm/", azs_views.FuelAzsConfirmView.as_view(), name="fuel-azs-confirm"),
    path("azs/stock/", azs_views.FuelAzsStockView.as_view(), name="fuel-azs-stock"),
    path("azs/verify/", azs_views.FuelAzsVerifyApiView.as_view(), name="fuel-azs-verify"),
    path("azs/sync/", azs_views.FuelAzsSyncApiView.as_view(), name="fuel-azs-sync"),
]

urlpatterns = [
    path("fuel/<fuelportal:subsystem_slug>/", include(fuel_urlpatterns)),
]
