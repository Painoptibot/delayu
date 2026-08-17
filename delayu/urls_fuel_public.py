"""URL публичного портала «Топливный пропуск» (граждане + АЗС)."""
from django.urls import include, path

from delayu import views_fuel_azs as azs_views
from delayu import views_fuel_public as views
from delayu import views_fuel_ufo_api as ufo_api
from delayu import views_fuel_ufo_web as ufo_web

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
    path(
        "redeems/<int:pk>/report/",
        views.FuelCitizenRedeemReportView.as_view(),
        name="fuel-redeem-report",
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

ufo_api_urlpatterns = [
    path("azs/", ufo_api.FuelUfoAzsListApi.as_view(), name="fuel-ufo-azs-list"),
    path("azs/<int:pk>/", ufo_api.FuelUfoAzsDetailApi.as_view(), name="fuel-ufo-azs-detail"),
    path("reports/", ufo_api.FuelUfoReportApi.as_view(), name="fuel-ufo-reports"),
    path("meta/", ufo_api.FuelUfoMetaApi.as_view(), name="fuel-ufo-meta"),
    path("geo-check/", ufo_api.FuelUfoGeoCheckApi.as_view(), name="fuel-ufo-geo-check"),
    path("route/", ufo_api.FuelUfoRouteApi.as_view(), name="fuel-ufo-route"),
    path("status/", ufo_api.FuelUfoStatusApi.as_view(), name="fuel-ufo-status"),
    path("stats/", ufo_api.FuelUfoStatsApi.as_view(), name="fuel-ufo-stats-api"),
    path("auth/start/", ufo_api.FuelUfoAuthStartApi.as_view(), name="fuel-ufo-auth-start"),
    path("auth/verify/", ufo_api.FuelUfoAuthVerifyApi.as_view(), name="fuel-ufo-auth-verify"),
    path("auth/me/", ufo_api.FuelUfoAuthMeApi.as_view(), name="fuel-ufo-auth-me"),
    path("auth/logout/", ufo_api.FuelUfoAuthLogoutApi.as_view(), name="fuel-ufo-auth-logout"),
]

urlpatterns = [
    path("fuel/<fuelportal:subsystem_slug>/", include(fuel_urlpatterns)),
    # Мобильное API ЮФО (без привязки к тенанту города)
    path("fuel/api/ufo/", include(ufo_api_urlpatterns)),
    path("fuel/ufo/app/", ufo_web.FuelUfoMobileMapView.as_view(), name="fuel-ufo-mobile-app"),
    path("fuel/ufo/legal/privacy/", ufo_web.FuelUfoLegalPrivacyView.as_view(), name="fuel-ufo-legal-privacy"),
    path("fuel/ufo/legal/rules/", ufo_web.FuelUfoLegalRulesView.as_view(), name="fuel-ufo-legal-rules"),
    path("fuel/ufo/support/", ufo_web.FuelUfoSupportView.as_view(), name="fuel-ufo-support"),
    path("fuel/ufo/android/", ufo_web.FuelUfoAndroidInstallView.as_view(), name="fuel-ufo-android"),
    path("fuel/ufo/stats/", ufo_web.FuelUfoStatsView.as_view(), name="fuel-ufo-stats"),
    path("fuel/ufo/android/fuel-ufo.apk", ufo_web.FuelUfoApkDownloadView.as_view(), name="fuel-ufo-apk"),
    path("fuel/ufo/sw.js", ufo_web.FuelUfoServiceWorkerView.as_view(), name="fuel-ufo-sw"),
]
