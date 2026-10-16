from delayu.services.uzhv_support_chat import ask_odysseus


def _ask(text: str) -> str:
    answer, engine = ask_odysseus(subsystem=None, history=[{"role": "user", "content": text}])
    assert engine.startswith("odysseus") or engine.startswith("llm:")
    assert "не отвечает" not in answer
    return answer


def test_odysseus_explains_how_to_open_cases():
    answer = _ask("Как открыть учёт нуждающихся?")
    assert "Учёт нуждающихся" in answer
    assert "/uzhv/cases/" in answer


def test_odysseus_explains_orphans_and_support():
    assert "/uzhv/orphans/" in _ask("Где раздел дети-сироты?")
    assert "Передать специалисту ТП" in _ask("Страница не открывается, ошибка доступа")


def test_odysseus_names_contour_logins():
    answer = _ask("Какой логин у начальника УЖВ?")
    assert "uzhv_mgr" in answer


def test_invented_password_is_replaced_by_the_handbook(monkeypatch):
    monkeypatch.setattr("delayu.services.uzhv_support_chat.llm_configured", lambda: True)
    monkeypatch.setattr(
        "delayu.services.uzhv_support_chat._ask_platform_llm",
        lambda *args, **kwargs: ("Пароль начальника — управление.", "delayu-uzhv"),
    )
    answer, engine = ask_odysseus(
        subsystem=None,
        history=[{"role": "user", "content": "Как открыть учёт нуждающихся?"}],
    )
    assert engine == "odysseus"
    assert "/uzhv/cases/" in answer
    assert "управление" not in answer


def test_odysseus_answers_when_the_model_is_off(monkeypatch):
    monkeypatch.setattr("delayu.services.uzhv_support_chat.llm_configured", lambda: False)
    monkeypatch.setattr(
        "delayu.services.uzhv_support_chat._ask_odysseus_service",
        lambda *args, **kwargs: "",
    )
    answer = _ask("Как открыть договоры?")
    assert "/uzhv/contracts/" in answer
