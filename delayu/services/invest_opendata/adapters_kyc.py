"""P0 KYC adapters (INN-based), mock-first."""
from __future__ import annotations

from delayu.services.invest_opendata.base import CheckContext, SourceResult
from delayu.services.invest_opendata.mock_fixtures import fixture_for_inn


def _fx(ctx: CheckContext) -> dict:
    return fixture_for_inn(ctx.inn)


class EgrulFnsAdapter:
    code = "egrul_fns"
    label = "ЕГРЮЛ / ЕГРИП (ФНС)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://egrul.nalog.ru/",
            )
        data = _fx(ctx)
        if ctx.live:
            # Live portals often require captcha; keep best-effort stub pointing to public UI.
            return SourceResult(
                source_code=self.code,
                status="ok",
                severity="info",
                title=self.label,
                payload={
                    "mode": "live_stub",
                    "inn": ctx.inn,
                    "hint": "Откройте карточку на egrul.nalog.ru; автоматический разбор HTML нестабилен.",
                },
                external_url=f"https://egrul.nalog.ru/",
            )
        severity = "hard" if not data.get("active") and data.get("bankrupt") else "info"
        if data.get("profile") == "empty":
            severity = "warn"
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity=severity,
            title=self.label,
            payload={
                "mode": "mock",
                "inn": ctx.inn,
                "name": data.get("name"),
                "ogrn": data.get("ogrn"),
                "status": data.get("status"),
                "active": data.get("active"),
            },
            external_url="https://egrul.nalog.ru/",
        )


class TransparentBusinessAdapter:
    code = "transparent_business"
    label = "Прозрачный бизнес (ФНС)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://pb.nalog.gov.ru/",
            )
        data = _fx(ctx)
        risks = list(data.get("pb_risks") or [])
        severity = "hard" if "банкротство" in risks else ("warn" if risks else "info")
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity=severity,
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "risks": risks},
            external_url="https://pb.nalog.gov.ru/",
        )


class BfoNalogAdapter:
    code = "bfo_nalog"
    label = "Бухотчётность (БФО ФНС)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://bo.nalog.gov.ru/",
            )
        data = _fx(ctx)
        years = list(data.get("bfo_years") or [])
        severity = "warn" if not years else "info"
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity=severity,
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "years": years},
            external_url="https://bo.nalog.gov.ru/",
        )


class FedresursAdapter:
    code = "fedresurs"
    label = "ЕФРСБ (банкротства)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://bankrot.fedresurs.ru/",
            )
        data = _fx(ctx)
        bankrupt = bool(data.get("bankrupt"))
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity="hard" if bankrupt else "info",
            title=self.label,
            payload={
                "mode": "mock" if ctx.mock else "live_stub",
                "inn": ctx.inn,
                "bankrupt": bankrupt,
            },
            external_url="https://bankrot.fedresurs.ru/",
        )


class FsspAdapter:
    code = "fssp"
    label = "ФССП (исполнительные производства)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://fssp.gov.ru/iss/ip/",
            )
        data = _fx(ctx)
        count = int(data.get("fssp_count") or 0)
        severity = "warn" if count > 0 else "info"
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity=severity,
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "count": count},
            external_url="https://fssp.gov.ru/iss/ip/",
        )


class KadArbitrAdapter:
    code = "kad_arbitr"
    label = "КАД (арбитраж)"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://kad.arbitr.ru/",
            )
        data = _fx(ctx)
        count = int(data.get("kad_count") or 0)
        severity = "warn" if count >= 3 else "info"
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity=severity,
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "cases": count},
            external_url="https://kad.arbitr.ru/",
        )


class EisRnpAdapter:
    code = "eis_rnp"
    label = "ЕИС / РНП"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://zakupki.gov.ru/",
            )
        data = _fx(ctx)
        in_rnp = bool(data.get("rnp"))
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity="hard" if in_rnp else "info",
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "in_rnp": in_rnp},
            external_url="https://zakupki.gov.ru/",
        )


class DisqualifiedAdapter:
    code = "disqualified"
    label = "Реестр дисквалифицированных лиц"
    entity_kinds = ("investor", "project")

    def check(self, ctx: CheckContext) -> SourceResult:
        if not ctx.inn:
            return SourceResult(
                source_code=self.code,
                status="empty",
                severity="warn",
                title=self.label,
                payload={"reason": "no_inn"},
                external_url="https://www.nalog.gov.ru/rn77/related_activities/registries/disqualified_persons/",
            )
        data = _fx(ctx)
        hit = bool(data.get("disqualified"))
        return SourceResult(
            source_code=self.code,
            status="ok",
            severity="hard" if hit else "info",
            title=self.label,
            payload={"mode": "mock" if ctx.mock else "live_stub", "inn": ctx.inn, "disqualified": hit},
            external_url="https://www.nalog.gov.ru/rn77/related_activities/registries/disqualified_persons/",
        )


KYC_ADAPTERS = [
    EgrulFnsAdapter(),
    TransparentBusinessAdapter(),
    BfoNalogAdapter(),
    FedresursAdapter(),
    FsspAdapter(),
    KadArbitrAdapter(),
    EisRnpAdapter(),
    DisqualifiedAdapter(),
]
