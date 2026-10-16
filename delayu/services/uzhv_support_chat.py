"""Ответ Odysseus в чате техподдержки контура УЖВ."""
from __future__ import annotations

import httpx
from django.conf import settings

from delayu.services.invest_ai_chat import llm_configured, llm_model_info
from delayu.services.uzhv_support_knowledge import answer_from_knowledge, handbook_for_prompt

SYSTEM_PROMPT = (
    "Ты Odysseus, помощник технической поддержки контура АИС УЖВ в системе ДелаЮ. "
    "Отвечай по-русски, коротко и по шагам, только по материалам ниже. "
    "Не выдумывай персональные данные, номера дел и суммы. "
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
            if answer:
                return answer, f"llm:{model}"
        except Exception:
            pass
    return grounded, "odysseus"


def _last_user_text(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get("role") == "user":
            return item.get("content") or ""
    return ""


def _prompt(question: str) -> str:
    return f"{SYSTEM_PROMPT}\n\nМатериалы:\n{handbook_for_prompt(question)}"


def _ask_odysseus_service(subsystem, history: list[dict], question: str) -> str:
    if subsystem is None:
        return ""
    from delayu.services.odysseus_settings import ensure_odysseus_settings

    cfg = ensure_odysseus_settings(subsystem)
    if not cfg.enabled or not (cfg.base_url or "").strip():
        return ""
    base = cfg.base_url.rstrip("/")
    messages = [{"role": "system", "content": _prompt(question)}]
    for item in history[-12:]:
        role = item.get("role")
        if role == "specialist":
            role = "assistant"
        if role in {"user", "assistant"} and (item.get("content") or "").strip():
            messages.append({"role": role, "content": item["content"][:4000]})
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
    messages = [{"role": "system", "content": _prompt(question)}]
    for item in history[-12:]:
        role = item.get("role")
        if role == "specialist":
            role = "assistant"
        if role in {"user", "assistant"} and (item.get("content") or "").strip():
            messages.append({"role": role, "content": item["content"][:4000]})
    last_error: Exception | None = None
    with httpx.Client(timeout=45.0) as client:
        for model in models:
            try:
                resp = client.post(
                    f"{base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": model, "messages": messages, "temperature": 0.2},
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
