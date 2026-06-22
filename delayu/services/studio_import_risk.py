"""Оценка риска импорта пакета конфигурации Студии."""
from __future__ import annotations


class ImportRiskError(Exception):
    """Импорт/откат заблокирован из-за критических изменений."""

    def __init__(self, risk: dict):
        self.risk = risk
        messages = [r["message"] for r in risk.get("critical") or []]
        super().__init__("; ".join(messages) or "Критические изменения")


RestoreRiskError = ImportRiskError

_CRITICAL_KEYS = frozenset({"policies", "integrations"})
_LIST_KEYS = ("forms", "bpm", "print", "nsi", "integrations")


def evaluate_config_change_risk(current: dict, incoming: dict) -> dict:
    """Критические изменения при импорте или откате (требует force=true)."""
    current = current or {}
    incoming = incoming or {}
    reasons: list[dict] = []

    for key in _LIST_KEYS:
        before_n = len(current.get(key) or [])
        after_n = len(incoming.get(key) or [])
        if before_n > 0 and after_n == 0:
            reasons.append(
                {
                    "key": key,
                    "level": "critical",
                    "message": f"Импорт удалит все записи в секции «{key}» ({before_n} → 0)",
                }
            )
        elif before_n > 0 and after_n < before_n // 2 and before_n >= 2:
            reasons.append(
                {
                    "key": key,
                    "level": "warning",
                    "message": f"Секция «{key}»: резкое сокращение ({before_n} → {after_n})",
                }
            )

    b_pol = current.get("policies") or {}
    a_pol = incoming.get("policies") or {}
    if b_pol or a_pol:
        if b_pol.get("siem_enabled") and not a_pol.get("siem_enabled"):
            reasons.append(
                {
                    "key": "policies",
                    "level": "critical",
                    "message": "Импорт отключит экспорт в SIEM",
                }
            )
        if b_pol.get("auto_purge") and not a_pol.get("auto_purge"):
            reasons.append(
                {
                    "key": "policies",
                    "level": "critical",
                    "message": "Импорт отключит авто-очистку архива",
                }
            )
        if a_pol and b_pol and a_pol != b_pol:
            reasons.append(
                {
                    "key": "policies",
                    "level": "warning",
                    "message": "Изменятся политики хранения/SIEM",
                }
            )

    b_int = {row.get("code") for row in (current.get("integrations") or []) if row.get("code")}
    a_int = {row.get("code") for row in (incoming.get("integrations") or []) if row.get("code")}
    removed_int = b_int - a_int
    if removed_int:
        reasons.append(
            {
                "key": "integrations",
                "level": "critical",
                "message": f"Импорт уберёт интеграции: {', '.join(sorted(removed_int)[:5])}",
            }
        )

    critical = [r for r in reasons if r["level"] == "critical"]
    return {
        "blocked": bool(critical),
        "critical": critical,
        "warnings": [r for r in reasons if r["level"] == "warning"],
        "reasons": reasons,
    }


evaluate_import_risk = evaluate_config_change_risk
evaluate_restore_risk = evaluate_config_change_risk
