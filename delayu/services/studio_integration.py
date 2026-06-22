"""Студия — dry-run pipeline интеграций."""
from __future__ import annotations

import copy
import re


def dry_run_pipeline(pipeline: dict, sample: dict | None = None) -> dict:
    """Тестовый прогон pipeline без отправки во внешние системы."""
    nodes = (pipeline or {}).get("nodes") or []
    if not nodes:
        return {"ok": False, "error": "empty", "log": [], "output": {}}

    data = copy.deepcopy(sample or {"id": 1, "title": "Тестовая запись", "status": "new"})
    log: list[dict] = []
    errors: list[str] = []

    for idx, node in enumerate(nodes, start=1):
        ntype = (node.get("type") or "step").lower()
        label = node.get("label") or ntype
        entry = {"step": idx, "type": ntype, "label": label, "status": "ok", "detail": ""}

        if ntype == "source":
            entry["detail"] = f"Загружено 1 запись: {data.get('title', '—')}"
        elif ntype == "map":
            mapping = node.get("mapping") or {"title": "subject"}
            mapped = {dst: data.get(src, "") for dst, src in mapping.items()}
            data.update(mapped)
            entry["detail"] = f"Смаплено полей: {len(mapping)}"
        elif ntype == "transform":
            expr = node.get("expr") or ""
            if expr:
                data["transformed"] = expr.replace("{{title}}", str(data.get("title", "")))
            entry["detail"] = "Трансформация применена"
        elif ntype == "validate":
            required = node.get("required") or ["title"]
            missing = [k for k in required if not str(data.get(k, "")).strip()]
            if missing:
                entry["status"] = "error"
                entry["detail"] = f"Нет полей: {', '.join(missing)}"
                errors.append(entry["detail"])
            else:
                entry["detail"] = "Валидация пройдена"
        elif ntype == "endpoint":
            entry["detail"] = f"Dry-run endpoint «{label}» — отправка пропущена"
        elif ntype == "smev":
            msg_type = node.get("message_type") or "Request"
            data["smev_envelope"] = {
                "message_type": msg_type,
                "status": "simulated",
                "note": "Этап 2 — без реальной отправки в СМЭВ",
            }
            entry["detail"] = f"СМЭВ stub: {msg_type} — конверт сформирован, отправка пропущена"
        elif ntype == "dry_run":
            entry["detail"] = "Контрольный прогон без записи"
        else:
            entry["detail"] = "Шаг выполнен"

        log.append(entry)
        if entry["status"] == "error":
            break

    return {
        "ok": not errors,
        "log": log,
        "output": data,
        "errors": errors,
        "records_in": 1,
        "records_out": 0 if errors else 1,
        "mode": "dry_run",
    }


def run_pipeline(
    pipeline: dict,
    *,
    sample: dict | None = None,
    mode: str = "dry_run",
    endpoint=None,
) -> dict:
    """Прогон pipeline: dry_run (без отправки) или runtime (СМЭВ через очередь)."""
    if mode != "runtime":
        result = dry_run_pipeline(pipeline, sample=sample)
        result["mode"] = "dry_run"
        return result

    nodes = (pipeline or {}).get("nodes") or []
    if not nodes:
        return {"ok": False, "error": "empty", "log": [], "output": {}, "mode": "runtime"}

    data = copy.deepcopy(sample or {"id": 1, "title": "Тестовая запись", "status": "new"})
    log: list[dict] = []
    errors: list[str] = []

    for idx, node in enumerate(nodes, start=1):
        ntype = (node.get("type") or "step").lower()
        label = node.get("label") or ntype
        entry = {"step": idx, "type": ntype, "label": label, "status": "ok", "detail": ""}

        if ntype == "source":
            entry["detail"] = f"Загружено 1 запись: {data.get('title', '—')}"
        elif ntype == "map":
            mapping = node.get("mapping") or {"title": "subject"}
            mapped = {dst: data.get(src, "") for dst, src in mapping.items()}
            data.update(mapped)
            entry["detail"] = f"Смаплено полей: {len(mapping)}"
        elif ntype == "validate":
            required = node.get("required") or ["title"]
            missing = [k for k in required if not str(data.get(k, "")).strip()]
            if missing:
                entry["status"] = "error"
                entry["detail"] = f"Нет полей: {', '.join(missing)}"
                errors.append(entry["detail"])
            else:
                entry["detail"] = "Валидация пройдена"
        elif ntype == "smev":
            if not endpoint:
                entry["status"] = "error"
                entry["detail"] = "Runtime: не выбран SMEV endpoint"
                errors.append(entry["detail"])
            else:
                from delayu.services.integrations import enqueue_outbound, process_outbound
                from delayu.services.smev_runtime import build_smev_envelope
                from delayu.models import IntegrationMessage

                msg_type = node.get("message_type") or "Request"
                payload = {
                    "message_type": msg_type,
                    "body": data,
                }
                msg = enqueue_outbound(endpoint, payload)
                msg = process_outbound(msg)
                msg.refresh_from_db()
                envelope = build_smev_envelope(payload, endpoint.config or {})
                data["smev_envelope"] = envelope
                data["smev_message_id"] = msg.pk
                data["smev_status"] = msg.status
                if msg.status == IntegrationMessage.Status.SENT:
                    entry["detail"] = f"СМЭВ runtime: MSG-{msg.pk} отправлено ({msg_type})"
                else:
                    entry["status"] = "error"
                    entry["detail"] = f"СМЭВ runtime: {msg.error_text or msg.status}"
                    errors.append(entry["detail"])
        elif ntype == "endpoint":
            entry["detail"] = f"Runtime endpoint «{label}» — пропущен (только СМЭВ)"
        else:
            entry["detail"] = "Шаг выполнен"

        log.append(entry)
        if entry["status"] == "error":
            break

    return {
        "ok": not errors,
        "log": log,
        "output": data,
        "errors": errors,
        "records_in": 1,
        "records_out": 0 if errors else 1,
        "mode": "runtime",
    }
