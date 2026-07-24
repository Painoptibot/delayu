from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from delayu.models import Organization, Subsystem
from delayu.models_invest import InvestRoadmapItem, InvestProject
from delayu.services.invest_roadmap import mark_overdue, overdue_items, seed_support_roadmap

User = get_user_model()

ROADMAP_DUE_OFFSETS = {
    "land": 14,
    "permits": 45,
    "build": 180,
    "commission": 365,
}


def assert_roadmap_sla_due_dates(items):
    today = timezone.now().date()
    by_code = {item.code: item for item in items}
    for code, days in ROADMAP_DUE_OFFSETS.items():
        assert by_code[code].due_at.date() == today + timedelta(days=days)


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
def test_overdue_items(invest_ctx):
    InvestRoadmapItem.objects.create(
        project=invest_ctx["project"],
        title="Земля",
        code="land",
        due_at=timezone.now() - timedelta(days=1),
        status="open",
    )
    qs = overdue_items(subsystem=invest_ctx["sub"])
    assert qs.count() == 1


@pytest.mark.django_db
def test_seed_support_roadmap(invest_ctx):
    items = seed_support_roadmap(invest_ctx["project"])
    assert len(items) == 4
    codes = [item.code for item in items]
    assert codes == ["land", "permits", "build", "commission"]
    assert all(item.status == InvestRoadmapItem.Status.OPEN for item in items)
    assert_roadmap_sla_due_dates(items)


@pytest.mark.django_db
def test_mark_overdue(invest_ctx):
    item = InvestRoadmapItem.objects.create(
        project=invest_ctx["project"],
        title="Земля",
        code="land",
        due_at=timezone.now() - timedelta(days=1),
        status="open",
    )
    updated = mark_overdue()
    assert updated == 1
    item.refresh_from_db()
    assert item.status == InvestRoadmapItem.Status.OVERDUE
