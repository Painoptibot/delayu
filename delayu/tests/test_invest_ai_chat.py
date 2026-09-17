from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import InvestProject
from delayu.services.invest_roles import perm_for_role
from delayu.services.odysseus_invest import (
    ROLE_AGENCY_SPECIALIST,
    ROLE_INTERNAL_ASSISTANT,
    SESSION_KEY,
    build_invest_odysseus_context,
    demo_starters_for_role,
    normalize_demo_role,
)
from delayu.services.odysseus_settings import ensure_odysseus_settings

User = get_user_model()


@pytest.fixture
def ai_chat_ctx(db):
    sub = Subsystem.objects.create(
        code="inv-ai-chat", name="Invest AI Chat", industry_template="invest", status="active"
    )
    module22, _ = ModuleCatalog.objects.get_or_create(code="M22", defaults={"name": "Инвестпроекты"})
    module87, _ = ModuleCatalog.objects.get_or_create(code="M87", defaults={"name": "Odysseus workspace"})
    SubsystemModule.objects.get_or_create(subsystem=sub, module=module22, defaults={"enabled": True})
    SubsystemModule.objects.get_or_create(subsystem=sub, module=module87, defaults={"enabled": True})
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    users = {}
    for code, name in [
        ("invest_admin", "Администратор"),
        ("invest_dept", "Департамент"),
        ("invest_agency", "Агентство"),
        ("invest_mo", "МО"),
    ]:
        role = Role.objects.create(subsystem=sub, code=code, name=name)
        RoleModulePermission.objects.create(role=role, module=module22, **perm_for_role(code, "M22"))
        RoleModulePermission.objects.create(role=role, module=module87, can_view=True)
        user = User.objects.create_user(f"ai_{code}", password="x")
        SubsystemMembership.objects.create(
            user=user, subsystem=sub, organization=org, role=role, is_default=True
        )
        users[code] = user
    project = InvestProject.objects.create(
        subsystem=sub,
        organization=org,
        code="P-AI-1",
        name="Проект AI-чат",
        investor_name="Инвестор",
        stage="lead",
    )
    cfg = ensure_odysseus_settings(sub)
    cfg.enabled = True
    cfg.role_allowlist = ["invest_admin", "invest_dept", "invest_agency"]
    cfg.save(update_fields=["enabled", "role_allowlist"])
    return {"sub": sub, "org": org, "users": users, "project": project, "cfg": cfg}


@pytest.mark.django_db
@pytest.mark.parametrize("role_code", ["invest_agency", "invest_dept", "invest_admin"])
def test_allowed_roles_get_ai_chat_200(client, ai_chat_ctx, role_code):
    client.force_login(ai_chat_ctx["users"][role_code])
    response = client.get(reverse("invest-ai-chat"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "ИИ-чат инвестора" in html
    assert "Специалист Агентства" in html
    assert "Помощник сотрудника" in html
    for phrase in demo_starters_for_role(ROLE_AGENCY_SPECIALIST):
        assert phrase in html


@pytest.mark.django_db
def test_mo_forbidden_on_ai_chat(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_mo"])
    response = client.get(reverse("invest-ai-chat"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_role_switch_stores_demo_role_in_session(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    response = client.post(
        reverse("invest-ai-chat"),
        {
            "role": ROLE_AGENCY_SPECIALIST,
            "project": ai_chat_ctx["project"].pk,
        },
    )
    assert response.status_code == 302
    ctx = client.session[SESSION_KEY]
    assert ctx["demo_role"] == ROLE_AGENCY_SPECIALIST
    assert ctx["project_id"] == ai_chat_ctx["project"].pk
    assert "специалист" in ctx["prompt_template"].lower()


@pytest.mark.django_db
def test_legacy_role_alias_maps_to_agency_specialist():
    assert normalize_demo_role("investor_rep") == ROLE_AGENCY_SPECIALIST
    assert normalize_demo_role("staff") == ROLE_INTERNAL_ASSISTANT


@pytest.mark.django_db
def test_starters_present_for_agency_specialist(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_dept"])
    response = client.get(reverse("invest-ai-chat"), {"role": ROLE_AGENCY_SPECIALIST})
    assert response.status_code == 200
    html = response.content.decode()
    for phrase in demo_starters_for_role(ROLE_AGENCY_SPECIALIST):
        assert phrase in html


@pytest.mark.django_db
def test_chat_works_without_odysseus(client, ai_chat_ctx):
    ai_chat_ctx["cfg"].enabled = False
    ai_chat_ctx["cfg"].save(update_fields=["enabled"])
    client.force_login(ai_chat_ctx["users"]["invest_admin"])
    response = client.get(reverse("invest-ai-chat"))
    assert response.status_code == 200
    html = response.content.decode()
    assert "invest-ai-chat-thread" in html
    assert "Открыть Odysseus" not in html
    assert 'title="Odysseus"' not in html


@pytest.mark.django_db
def test_in_page_chat_message_endpoint(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_INTERNAL_ASSISTANT, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"Что сейчас не хватает в пакете документов?"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["reply"]
    assert any(m["role"] == "assistant" for m in payload["messages"])


@pytest.mark.django_db
def test_weekday_question_uses_system_clock(client, ai_chat_ctx):
    from django.utils import timezone

    from delayu.services.invest_ai_chat import _WEEKDAYS_RU

    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_AGENCY_SPECIALIST, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"какой сегодня день недели?"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["engine"] == "system"
    weekday = _WEEKDAYS_RU[timezone.localtime(timezone.now()).weekday()]
    assert weekday in payload["reply"].lower()
    assert timezone.localtime(timezone.now()).strftime("%d.%m.%Y") in payload["reply"]


@pytest.mark.django_db
def test_build_context_internal_assistant_prompt(ai_chat_ctx):
    ctx = build_invest_odysseus_context(
        subsystem=ai_chat_ctx["sub"],
        project=ai_chat_ctx["project"],
        role=ROLE_INTERNAL_ASSISTANT,
    )
    assert ctx["demo_role"] == ROLE_INTERNAL_ASSISTANT
    assert ctx["starters"] == demo_starters_for_role(ROLE_INTERNAL_ASSISTANT)
    assert "помощник" in ctx["prompt_template"].lower()


@pytest.mark.django_db
def test_department_head_name_does_not_hallucinate(client, ai_chat_ctx, settings):
    # Even with LLM configured, identity questions must stay system-grounded.
    settings.DELAYU_LLM_BASE_URL = "http://127.0.0.1:11434/v1"
    settings.DELAYU_LLM_API_KEY = "ollama"
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_AGENCY_SPECIALIST, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"как зовут руководителя департамента инвестиций?"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["engine"] == "system"
    assert payload["offer_specialist"] is True
    low = payload["reply"].lower()
    assert "нет" in low or "не " in low
    assert "анна" not in low and "сергей" not in low
    assert "специалист" in low


@pytest.mark.django_db
def test_unknown_answer_offers_specialist(client, ai_chat_ctx, settings):
    settings.DELAYU_LLM_BASE_URL = ""
    settings.DELAYU_LLM_API_KEY = ""
    settings.OPENAI_API_KEY = ""
    settings.OPENAI_BASE_URL = ""
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_AGENCY_SPECIALIST, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"Какой точный ROI инвестора за 2027 год по закрытому NDA?"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["offer_specialist"] is True
    assert "специалист" in payload["reply"].lower()
    assert "[ESCALATE_SPECIALIST]" not in payload["reply"]


@pytest.mark.django_db
def test_escalate_action_creates_request(client, ai_chat_ctx):
    from delayu.models_invest import InvestProjectComment
    from delayu.services.invest_ai_chat import ESCALATION_SESSION_KEY

    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_AGENCY_SPECIALIST, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"action":"escalate","question":"Нужна точная сумма льгот"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["offer_specialist"] is False
    assert payload["escalation"]["status"] == "requested"
    assert "Заявка специалисту" in payload["reply"]
    assert client.session[ESCALATION_SESSION_KEY]["status"] == "requested"
    assert InvestProjectComment.objects.filter(
        project=ai_chat_ctx["project"], body__contains="подключение специалиста"
    ).exists()


@pytest.mark.django_db
def test_user_phrase_triggers_specialist(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_INTERNAL_ASSISTANT, "project": ai_chat_ctx["project"].pk},
    )
    response = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"Подключите специалиста, пожалуйста"}',
        content_type="application/json",
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["escalation"]["status"] == "requested"
    assert payload["engine"] == "escalation"


@pytest.mark.django_db
def test_briefing_and_specialist_timeline(client, ai_chat_ctx):
    client.force_login(ai_chat_ctx["users"]["invest_dept"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_INTERNAL_ASSISTANT, "project": ai_chat_ctx["project"].pk},
    )
    page = client.get(reverse("invest-ai-chat"), {"role": ROLE_INTERNAL_ASSISTANT, "applied": "1", "project": ai_chat_ctx["project"].pk})
    html = page.content.decode()
    assert "Примеры вопросов" in html
    assert "Журнал" in html
    assert "Сводка" in html
    assert "Очередь специалиста" in html
    assert "Только факты карточки" in html
    assert "Демо за 3 минуты" not in html
    assert "Журнал для руководства" not in html

    briefing = client.post(
        reverse("invest-ai-chat-message"),
        data='{"action":"briefing"}',
        content_type="application/json",
    ).json()
    assert briefing["ok"] is True
    assert briefing["grounding"] == "briefing"
    assert "Сводка для совещания" in briefing["reply"]
    assert briefing["sources"]

    esc = client.post(
        reverse("invest-ai-chat-message"),
        data='{"action":"escalate","question":"Уточнить льготы"}',
        content_type="application/json",
    ).json()
    assert esc["escalation"]["timeline"]
    assert esc["escalation"]["sla_minutes"] == 15
    assert esc["escalation"]["ticket_id"]

    from delayu.models import Notification
    from delayu.models_invest import InvestAiChatTicket

    assert InvestAiChatTicket.objects.filter(pk=esc["escalation"]["ticket_id"]).exists()
    assert Notification.objects.filter(title__contains="заявка специалисту").exists()

    pdf = client.get(reverse("invest-ai-chat-export-pdf"))
    assert pdf.status_code == 200
    assert pdf["Content-Type"] == "application/pdf"

    docx = client.get(reverse("invest-ai-chat-export-docx"))
    assert docx.status_code == 200
    assert "wordprocessingml" in docx["Content-Type"]

    accepted = client.post(
        reverse("invest-ai-chat-message"),
        data='{"action":"escalation_accept"}',
        content_type="application/json",
    ).json()
    assert accepted["escalation"]["status"] == "accepted"

    joined = client.post(
        reverse("invest-ai-chat-message"),
        data='{"action":"specialist_reply","message":"Льготы уточним официальным письмом."}',
        content_type="application/json",
    ).json()
    assert joined["grounding"] == "specialist"
    assert joined["escalation"]["status"] == "joined"
    assert any(m["role"] == "specialist" for m in joined["messages"])


@pytest.mark.django_db
def test_package_answer_includes_sources(client, ai_chat_ctx, settings):
    settings.DELAYU_LLM_BASE_URL = ""
    settings.DELAYU_LLM_API_KEY = ""
    settings.OPENAI_API_KEY = ""
    settings.OPENAI_BASE_URL = ""
    client.force_login(ai_chat_ctx["users"]["invest_agency"])
    client.post(
        reverse("invest-ai-chat"),
        {"role": ROLE_AGENCY_SPECIALIST, "project": ai_chat_ctx["project"].pk},
    )
    payload = client.post(
        reverse("invest-ai-chat-message"),
        data='{"message":"Какие документы нужны в пакете для передачи в Департамент?"}',
        content_type="application/json",
    ).json()
    assert payload["ok"] is True
    assert payload["provenance_label"]
    assert payload["sources"]
