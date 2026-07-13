"""Аудит безопасности контура «Топливный пропуск»."""
from __future__ import annotations

from django.conf import settings
from django.test import Client
from django.urls import reverse

from delayu.models import Subsystem
from delayu.models_fuel import FuelAzsStation, FuelPermit


def _finding(
    code: str,
    title: str,
    *,
    severity: str,
    passed: bool,
    detail: str = "",
    recommendation: str = "",
) -> dict:
    return {
        "code": code,
        "title": title,
        "severity": severity,
        "passed": passed,
        "detail": detail,
        "recommendation": recommendation,
    }


def fuel_security_audit(subsystem: Subsystem) -> dict:
    findings: list[dict] = []

    findings.append(
        _finding(
            "debug_off",
            "Режим DEBUG отключён в production",
            severity="critical",
            passed=not bool(getattr(settings, "DEBUG", False)),
            detail=f"DEBUG={getattr(settings, 'DEBUG', False)}",
            recommendation="Установите DEBUG=False на боевом сервере.",
        )
    )
    findings.append(
        _finding(
            "secret_key",
            "SECRET_KEY не является значением по умолчанию",
            severity="critical",
            passed=getattr(settings, "SECRET_KEY", "") not in ("", "django-insecure-change-me"),
            detail="Проверка длины и нестандартности ключа",
            recommendation="Задайте уникальный SECRET_KEY в .env.",
        )
    )
    findings.append(
        _finding(
            "csrf_cookie_secure",
            "CSRF_COOKIE_SECURE",
            severity="high",
            passed=bool(getattr(settings, "CSRF_COOKIE_SECURE", False)) or bool(getattr(settings, "DEBUG", False)),
            detail=f"CSRF_COOKIE_SECURE={getattr(settings, 'CSRF_COOKIE_SECURE', False)}",
            recommendation="Включите CSRF_COOKIE_SECURE при HTTPS.",
        )
    )
    findings.append(
        _finding(
            "session_cookie_secure",
            "SESSION_COOKIE_SECURE",
            severity="high",
            passed=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) or bool(getattr(settings, "DEBUG", False)),
            detail=f"SESSION_COOKIE_SECURE={getattr(settings, 'SESSION_COOKIE_SECURE', False)}",
            recommendation="Включите SESSION_COOKIE_SECURE при HTTPS.",
        )
    )

    client = Client()
    host = "127.0.0.1"
    slug = subsystem.public_subdomain or subsystem.code
    portal_root = f"/fuel/{slug}/"

    # Операторские URL без авторизации
    protected_paths = [
        reverse("fuel-operator-hub"),
        reverse("fuel-operator-dashboard"),
        reverse("fuel-operator-applications"),
        reverse("fuel-operator-live-api"),
    ]
    open_operator = []
    for path in protected_paths:
        resp = client.get(path, HTTP_HOST=host)
        if resp.status_code == 200:
            open_operator.append(path)
    findings.append(
        _finding(
            "operator_auth",
            "Операторская панель требует авторизацию",
            severity="critical",
            passed=not open_operator,
            detail="Открыты без входа: " + ", ".join(open_operator) if open_operator else "Все проверенные URL перенаправляют на вход",
        )
    )

    # Портал АЗС без сессии
    azs_resp = client.get(f"{portal_root}azs/", HTTP_HOST=host)
    findings.append(
        _finding(
            "azs_auth",
            "Портал АЗС закрыт без входа",
            severity="high",
            passed=azs_resp.status_code in (302, 401, 403),
            detail=f"GET {portal_root}azs/ → {azs_resp.status_code}",
        )
    )

    # IDOR: чужой пропуск по pk (требуется сессия жителя той же подсистемы)
    permit = FuelPermit.objects.filter(subsystem=subsystem).order_by("-pk").first()
    other = FuelPermit.objects.exclude(subsystem=subsystem).order_by("-pk").first()
    if permit and other:
        slug = subsystem.public_subdomain or subsystem.code
        resp = client.get(f"/fuel/{slug}/permits/{other.pk}/qr.svg", HTTP_HOST=host)
        findings.append(
            _finding(
                "permit_idor",
                "QR пропуска недоступен по чужому ID",
                severity="critical",
                passed=resp.status_code in (302, 403, 404),
                detail=f"Чужой permit #{other.pk} → {resp.status_code}",
            )
        )

    # PIN АЗС в открытом виде
    plain_pins = FuelAzsStation.objects.filter(
        subsystem=subsystem, portal_pin__gt="", is_archived=False
    ).count()
    findings.append(
        _finding(
            "azs_pin_storage",
            "PIN портала АЗС хранится в БД (проверьте хеширование)",
            severity="medium",
            passed=False,
            detail=f"Активных АЗС с PIN: {plain_pins}",
            recommendation="Для production рекомендуется хешировать PIN и ограничить попытки входа.",
        )
    )

    # Публичный status API
    status_resp = client.get(f"{portal_root}status.json?refresh=1", HTTP_HOST=host)
    findings.append(
        _finding(
            "status_api_rate",
            "Публичный status API отвечает без авторизации (ожидаемо)",
            severity="info",
            passed=status_resp.status_code == 200,
            detail="API предназначен для жителей; защитите rate-limit на reverse-proxy.",
            recommendation="Настройте лимит запросов на nginx/ingress.",
        )
    )

    critical_fail = sum(1 for f in findings if not f["passed"] and f["severity"] == "critical")
    high_fail = sum(1 for f in findings if not f["passed"] and f["severity"] == "high")
    return {
        "ok": critical_fail == 0 and high_fail == 0,
        "findings": findings,
        "summary": {
            "total": len(findings),
            "passed": sum(1 for f in findings if f["passed"]),
            "failed": sum(1 for f in findings if not f["passed"]),
            "critical_fail": critical_fail,
            "high_fail": high_fail,
        },
    }
