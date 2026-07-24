import pytest
from django.contrib.auth import get_user_model
from delayu.models import Organization, Subsystem
from delayu.models_invest import InvestProject

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
def test_package_blocks_when_required_missing(invest_ctx):
    from delayu.services.invest_package import ensure_package, package_is_ready

    pkg = ensure_package(invest_ctx["project"])
    assert package_is_ready(invest_ctx["project"]) is False
    for item in pkg.items.filter(required=True):
        item.status = "attached"
        item.save(update_fields=["status"])
    assert package_is_ready(invest_ctx["project"]) is True


@pytest.mark.django_db
def test_no_package_is_ready(invest_ctx):
    from delayu.services.invest_package import package_is_ready

    assert package_is_ready(invest_ctx["project"]) is True
