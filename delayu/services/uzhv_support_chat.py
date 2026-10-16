"""Ответ Odysseus в чате техподдержки контура УЖВ."""
from __future__ import annotations

import re

import httpx
from django.conf import settings

from delayu.services.invest_ai_chat import llm_configured, llm_model_info
from delayu.services.uzhv_support_knowledge import answer_from_knowledge, handbook_for_prompt

SYSTEM_PROMPT = (
    "Ты Odysseus, помощник технической поддержки контура АИС УЖВ в системе ДелаЮ. "
    "Отвечай по-русски, коротко и по шагам, только на заданный вопрос и только по материалам ниже. "
    "Не перечисляй соседние разделы, о которых не спросили. "
    "Логины, роли и адреса из материалов называй прямо. "
    "Не выдумывай других логинов, персональные данные, номера дел и суммы. "
    "Если в материалах нет ответа, так и скажи и предложи кнопку «Передать специалисту ТП»."
)


def offline_reply(question: str) -> str:
    snippet = (question or "").strip().replace("\n", " ")[:180]
    return (
        "Я Odysseus. На этом стенде языковая модель сейчас не отвечает, "
        "поэтому я сохранил сообщение в обращении. "
        "Если нужен человек, нажмите «Передать специалисту ТП». "
        "Пока проверьте: вы вошли под своей ролью, нужный раздел есть в меню слева, "
        "номер дела начинается с УЖВ-2026-. "
        f"Ваш вопрос сохранён: «{snippet}»."
    )


def ask_odysseus(*, subsystem, history: list[dict]) -> tuple[str, str]:
    """Вернуть текст ответа и имя движка: odysseus или llm:<модель>."""
    question = _last_user_text(history)
    grounded = answer_from_knowledge(question)
    text = _ask_odysseus_service(subsystem, history, question)
    if text:
        return text, "odysseus"
    if llm_configured():
        try:
            answer, model = _ask_platform_llm(history, question)
            if answer and _model_answer_is_safe(answer):
                return answer, f"llm:{model}"
        except Exception:
            pass
    return grounded, "odysseus"


_KNOWN_LOGINS = (
    "uzhv_mgr",
    "uzhv_spec",
    "uzhv_orphan",
    "uzhv_contract",
    "uzhv_admin",
    "invest_admin",
    "invest_agency",
    "invest_dept",
    "invest_mo",
    "invest_viewer",
    "fuel_nvr",
)


def _model_answer_is_safe(answer: str) -> bool:
    """Маленькая модель иногда выдумывает пароль. Такой ответ в чат не отдаём."""
    text = (answer or "").lower().replace("ё", "е")
    if not text.strip() or "не отвечает" in text:
        return False
    for match in re.finditer(r"парол\w*.{0,48}", text):
        window = match.group(0)
        if "совпада" in window:
            continue
        if any(login in window for login in _KNOWN_LOGINS):
            continue
        return False
    return True


def _last_user_text(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get("role") == "user":
            return item.get("content") or ""
    return ""


def _prompt(question: str, *, compact: bool = False) -> str:
    return f"{SYSTEM_PROMPT}\n\nМатериалы:\n{handbook_for_prompt(question, compact=compact)}"


def _small_model(name: str) -> bool:
    return "0.5" in (name or "") or (name or "").startswith("delayu-uzhv")


def _messages(history: list[dict], question: str, *, compact: bool = False) -> list[dict]:
    messages = [{"role": "system", "content": _prompt(question, compact=compact)}]
    for item in history[-12:]:
        role = item.get("role")
        if role == "specialist":
            role = "assistant"
        if role in {"user", "assistant"} and (item.get("content") or "").strip():
            messages.append({"role": role, "content": item["content"][:4000]})
    return messages


def _ask_odysseus_service(subsystem, history: list[dict], question: str) -> str:
    if subsystem is None:
        return ""
    from delayu.services.odysseus_settings import ensure_odysseus_settings

    cfg = ensure_odysseus_settings(subsystem)
    if not cfg.enabled or not (cfg.base_url or "").strip():
        return ""
    base = cfg.base_url.rstrip("/")
    messages = _messages(history, question)
    try:
        with httpx.Client(timeout=12.0) as client:
            resp = client.post(
                f"{base}/v1/chat/completions",
                json={"model": "odysseus", "messages": messages, "temperature": 0.2},
            )
        if resp.status_code >= 400:
            return ""
        data = resp.json()
        return (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
    except Exception:
        return ""


def _ask_platform_llm(history: list[dict], question: str) -> tuple[str, str]:
    api_key = (
        getattr(settings, "DELAYU_LLM_API_KEY", "")
        or getattr(settings, "OPENAI_API_KEY", "")
        or "ollama"
    )
    base = (
        getattr(settings, "DELAYU_LLM_BASE_URL", "")
        or getattr(settings, "OPENAI_BASE_URL", "")
        or "https://api.openai.com/v1"
    ).rstrip("/")
    info = llm_model_info()
    models = [info["primary"]]
    if info["fallback"] and info["fallback"] not in models:
        models.append(info["fallback"])
    last_error: Exception | None = None
    with httpx.Client(timeout=20.0) as client:
        for model in models:
            messages = _messages(history, question, compact=_small_model(model))
            try:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 400,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                text = (
                    ((data.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                ).strip()
                if text:
                    return text, model
            except Exception as exc:
                last_error = exc
    if last_error:
        raise last_error
    return "", models[0]
