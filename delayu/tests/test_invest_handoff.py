import pytest
from django.contrib.auth import get_user_model
from delayu.models import Organization, Subsystem
from delayu.models_invest import InvestHandoff, InvestProject, InvestRoadmapItem
from delayu.services.invest_handoff import (
    InvestHandoffError,
    accept_handoff,
    request_handoff,
    return_handoff,
)

User = get_user_model()


@pytest.fixture
def invest_ctx(db):
    sub = Subsystem.objects.create(code="inv-b", name="B", industry_template="invest", status="active")
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    user = User.objects.create_user("inv_u", password="x")
    project = InvestProject.objects.create(
        subsystem=sub,
        code="P-1",
        name="Проект 1",
        organization=org,
        funnel=InvestProject.Funnel.ATTRACTION,
        stage="site_pick",
    )
    return {"sub": sub, "org": org, "user": user, "project": project}


@pytest.mark.django_db
def test_accept_moves_to_support(invest_ctx):
    p = invest_ctx["project"]
    p.stage = "package_ready"
    p.save(update_fields=["stage"])
    h = request_handoff(project=p, user=invest_ctx["user"])
    accept_handoff(handoff=h, user=invest_ctx["user"])
    p.refresh_from_db()
    assert p.funnel == InvestProject.Funnel.SUPPORT
    assert p.stage == "accepted"
    h.refresh_from_db()
    assert h.status == InvestHandoff.Status.ACCEPTED
    assert p.roadmap_items.count() == 4
    assert set(p.roadmap_items.values_list("code", flat=True)) == {
        "land",
        "permits",
        "build",
        "commission",
    }
    assert all(item.status == InvestRoadmapItem.Status.OPEN for item in p.roadmap_items.all())


@pytest.mark.django_db
def test_direct_funnel_change_not_via_model_save_helper():
    assert hasattr(InvestProject.Funnel, "ATTRACTION")


@pytest.mark.django_db
def test_return_keeps_attraction(invest_ctx):
    p = invest_ctx["project"]
    p.stage = "package_ready"
    p.save(update_fields=["stage"])
    h = request_handoff(project=p, user=invest_ctx["user"])
    return_handoff(handoff=h, user=invest_ctx["user"], comment="Неполный пакет")
    p.refresh_from_db()
    assert p.funnel == InvestProject.Funnel.ATTRACTION
    h.refresh_from_db()
    assert h.status == InvestHandoff.Status.RETURNED


@pytest.mark.django_db
def test_request_handoff_blocked_when_not_attraction(invest_ctx):
    p = invest_ctx["project"]
    p.funnel = InvestProject.Funnel.SUPPORT
    p.save(update_fields=["funnel"])
    with pytest.raises(InvestHandoffError, match="Передача только из воронки привлечения"):
        request_handoff(project=p, user=invest_ctx["user"])


@pytest.mark.django_db
def test_accept_blocked_when_package_not_ready(invest_ctx, monkeypatch):
    monkeypatch.setattr("delayu.services.invest_handoff.package_is_ready", lambda project: False)
    p = invest_ctx["project"]
    p.stage = "package_ready"
    p.save(update_fields=["stage"])
    h = request_handoff(project=p, user=invest_ctx["user"])
    with pytest.raises(InvestHandoffError):
        accept_handoff(handoff=h, user=invest_ctx["user"])
