"""P0 site adapters (cadastral / local store), mock-first."""
from __future__ import annotations

from delayu.services.invest_opendata.base import CheckContext, SourceResult
from delayu.services.invest_opendata.mock_fixtures import fixture_for_cadastral


class NspdPublicAdapter:
    code = "nspd_public"
    label = "НСПД / публичные сведения ЗУ"
    entity_kinds = ("site",)

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.cadastral:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_cadastral"},
                external_url="https://nspd.gov.ru/",
            )
        data = fixture_for_cadastral(ctx.cadastral)
        found = bool(data.get("found") and data.get("nspd"))
        return SourceResult(
            source_code=self.code,
            status="ok" if found else "empty",
            severity="info" if found else "warn",
            title=self.label,
            payload={
                "mode": "mock" if ctx.mock else "live_stub",
                "cadastral": ctx.cadastral,
                "found": found,
                "address": data.get("address") or "",
                "area_ha": data.get("area_ha"),
                "lat": ctx.latitude,
                "lon": ctx.longitude,
            },
            external_url="https://nspd.gov.ru/",
        )


class FgistpPublicAdapter:
    code = "fgistp_public"
    label = "ФГИС ТП (публичный каталог)"
    entity_kinds = ("site",)

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.cadastral:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_cadastral"},
                external_url="https://fgistp.economy.gov.ru/",
            )
        # Prefer local mock FGISTP document search when available
        docs_count = 0
        try:
            from delayu.services.invest_fgistp import search_fgistp_documents

            if ctx.site is not None:
                hits = search_fgistp_documents(
                    subsystem=ctx.subsystem,
                    q=ctx.cadastral,
                    limit=10,
                )
                docs_count = len(hits or [])
        except Exception:  # noqa: BLE001
            data = fixture_for_cadastral(ctx.cadastral)
            docs_count = int(data.get("fgistp_docs") or 0)
        if docs_count == 0:
            data = fixture_for_cadastral(ctx.cadastral)
            docs_count = int(data.get("fgistp_docs") or 0)
        return SourceResult(
            source_code=self.code,
            status="ok" if docs_count else "empty",
            severity="info" if docs_count else "warn",
            title=self.label,
            payload={
                "mode": "mock" if ctx.mock else "live_stub",
                "cadastral": ctx.cadastral,
                "documents": docs_count,
            },
            external_url="https://fgistp.economy.gov.ru/",
        )


class MnpLocalAdapter:
    code = "mnp_local"
    label = "МНП генплан (локальный store)"
    entity_kinds = ("site",)

    def check(self, ctx: CheckContext) -> SourceResult:
        from delayu.services.invest_mnp_store import store_status

        st = store_status()
        zones = 0
        hard = 0
        # If site has latest extract with geometry, reuse intersection snapshot if present
        if ctx.site is not None:
            extract = getattr(ctx.site, "extracts", None)
            if extract is not None:
                latest = ctx.site.extracts.order_by("-updated_at").first()
                if latest and latest.geometry:
                    try:
                        from delayu.services.invest_extract_mnp import (
                            find_mnp_intersections,
                            intersections_from_extract,
                        )

                        snap = intersections_from_extract(latest)
                        if not snap.get("computed_at"):
                            snap = find_mnp_intersections(latest.geometry)
                        zones = int(snap.get("count") or 0)
                        hard = int(snap.get("hard_count") or 0)
                    except Exception:  # noqa: BLE001
                        data = fixture_for_cadastral(ctx.cadastral)
                        zones = int(data.get("mnp_zones") or 0)
                        hard = int(data.get("mnp_hard") or 0)
        if zones == 0 and hard == 0 and ctx.mock:
            data = fixture_for_cadastral(ctx.cadastral)
            if data.get("found"):
                zones = int(data.get("mnp_zones") or 0)
                hard = int(data.get("mnp_hard") or 0)
        severity = "hard" if hard else "info"
        status = "ok" if not st.get("empty") or zones else "empty"
        return SourceResult(
            source_code=self.code,
            status=status,
            severity=severity,
            title=self.label,
            payload={
                "mode": "local_store",
                "store": st,
                "zones": zones,
                "hard_count": hard,
                "cadastral": ctx.cadastral,
            },
            external_url="",
        )


SITE_ADAPTERS = [
    NspdPublicAdapter(),
    FgistpPublicAdapter(),
    MnpLocalAdapter(),
]
