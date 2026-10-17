from delayu.services.uzhv_support_chat import ask_odysseus
from delayu.services.uzhv_support_knowledge import answer_from_knowledge


def _ask(text: str) -> str:
    answer = answer_from_knowledge(text)
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


def test_handbook_cites_the_current_housing_law():
    queue = _ask("По какому закону ставят на учёт нуждающихся?")
    assert "1655-КЗ" in queue
    assert "статье 51" in queue or "статьи 49, 51" in queue
    poor = _ask("Какой закон регулирует признание малоимущими?")
    assert "1890-КЗ" in poor
    assert "30 рабочих дней" in poor
    orphans = _ask("Какой закон про жильё детей-сирот?")
    assert "159-ФЗ" in orphans
    appeals = _ask("Какой срок ответа на обращение по 59-ФЗ?")
    assert "59-ФЗ" in appeals
    base = _ask("Какая законодательная база у АИС УЖВ?")
    assert "1655-КЗ" in base
    assert "1890-КЗ" in base


def test_handbook_covers_fields_and_neighbouring_screens():
    low = _ask("Как заполнить заключение о малоимущих?")
    assert "Доход проверен" in low
    assert "Отдельного пункта меню «Малоимущие» нет" in low
    reports = _ask("Как выгрузить ОТЧ-1?")
    assert "ОТЧ-1" in reports
    assert "/uzhv/reports/" in reports
    appeals = _ask("Какой срок ответа на обращение?")
    assert "30 календарных дней" in appeals
    accounts = _ask("Где выписка по лицевому счету?")
    assert "Выписка" in accounts
    assert "/uzhv/fund/accounts/" in accounts
    orders = _ask("Где предписания на проверку?")
    assert "/uzhv/inspection-orders/" in orders
    fix = _ask("Где предписания об устранении?")
    assert "/uzhv/prescriptions/" in fix
    lists = _ask("Что делает значок глаза и карандаш?")
    assert "просмотр" in lists
    assert "Наблюдатель" in lists or "наблюдател" in lists.lower()


def test_odysseus_answers_when_the_model_is_off(monkeypatch):
    monkeypatch.setattr("delayu.services.uzhv_support_chat.llm_configured", lambda: False)
    monkeypatch.setattr(
        "delayu.services.uzhv_support_chat._ask_odysseus_service",
        lambda *args, **kwargs: "",
    )
    answer = _ask("Как открыть договоры?")
    assert "/uzhv/contracts/" in answer
