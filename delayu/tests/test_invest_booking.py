import pytest
from django.contrib.auth import get_user_model
from delayu.models import Organization, Subsystem
from delayu.models_invest import InvestProject, InvestSite, InvestProjectSite
from delayu.services.invest_booking import InvestBookingError, book_site, select_site

User = get_user_model()


@pytest.fixture
def invest_ctx(db):
    sub = Subsystem.objects.create(code="inv-b", name="B", industry_template="invest", status="active")
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    user = User.objects.create_user("inv_u", password="x")
    project = InvestProject.objects.create(
        subsystem=sub, code="P-1", name="Проект 1", organization=org,
        funnel=InvestProject.Funnel.ATTRACTION, stage="site_pick",
    )
    site = InvestSite.objects.create(
        subsystem=sub, cadastral_number="23:00:0000000:1", name="ЗУ-1",
        organization=org, status=InvestSite.Status.ACTUAL,
    )
    return {"sub": sub, "org": org, "user": user, "project": project, "site": site}


@pytest.mark.django_db
def test_book_site_ok(invest_ctx):
    link = book_site(project=invest_ctx["project"], site=invest_ctx["site"], user=invest_ctx["user"])
    assert link.role == InvestProjectSite.Role.BOOKED


@pytest.mark.django_db
def test_second_book_blocked(invest_ctx):
    book_site(project=invest_ctx["project"], site=invest_ctx["site"], user=invest_ctx["user"])
    p2 = InvestProject.objects.create(
        subsystem=invest_ctx["sub"], code="P-2", name="Проект 2",
        organization=invest_ctx["org"], funnel="attraction", stage="site_pick",
    )
    with pytest.raises(InvestBookingError):
        book_site(project=p2, site=invest_ctx["site"], user=invest_ctx["user"])


@pytest.mark.django_db
def test_book_rejects_cross_subsystem(invest_ctx):
    sub2 = Subsystem.objects.create(code="inv-c", name="C", industry_template="invest", status="active")
    org2 = Organization.objects.create(subsystem=sub2, code="mo2", name="МО-2")
    project2 = InvestProject.objects.create(
        subsystem=sub2, code="P-x", name="Проект X", organization=org2,
        funnel=InvestProject.Funnel.ATTRACTION, stage="site_pick",
    )
    with pytest.raises(InvestBookingError, match="разным подсистемам"):
        book_site(project=project2, site=invest_ctx["site"], user=invest_ctx["user"])


@pytest.mark.django_db
def test_select_requires_booked_or_promotes(invest_ctx):
    book_site(project=invest_ctx["project"], site=invest_ctx["site"], user=invest_ctx["user"])
    link = select_site(project=invest_ctx["project"], site=invest_ctx["site"], user=invest_ctx["user"])
    assert link.role == InvestProjectSite.Role.SELECTED
