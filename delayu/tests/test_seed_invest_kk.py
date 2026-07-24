import pytest
from django.core.management import call_command

from delayu.models import Subsystem, SubsystemModule
from delayu.models_invest import (
    InvestHandoff,
    InvestPackage,
    InvestProject,
    InvestProjectSite,
    InvestRoadmapItem,
    InvestSite,
)


@pytest.mark.django_db
def test_seed_invest_kk_creates_demo_contour():
    call_command("seed_invest_kk", verbosity=0)

    subsystem = Subsystem.objects.get(code="invest-kk")
    assert subsystem.industry_template == "invest"
    assert subsystem.status == Subsystem.Status.ACTIVE
    assert subsystem.primary_color == "#0f766e"
    assert subsystem.invest_projects.count() == 3
    assert subsystem.invest_sites.count() == 4
    assert InvestProjectSite.objects.filter(
        project__subsystem=subsystem, role=InvestProjectSite.Role.BOOKED
    ).exists()
    assert InvestHandoff.objects.filter(
        project__subsystem=subsystem, status=InvestHandoff.Status.REQUESTED
    ).exists()
    assert InvestPackage.objects.filter(project__subsystem=subsystem).count() >= 2
    assert InvestRoadmapItem.objects.filter(
        project__subsystem=subsystem,
        project__funnel=InvestProject.Funnel.SUPPORT,
    ).count() == 4
    assert (
        SubsystemModule.objects.filter(
            subsystem=subsystem,
            module__code__in=("M02", "M03", "M15", "M22"),
            enabled=True,
        ).count()
        == 4
    )
    assert InvestSite.objects.filter(subsystem=subsystem).count() == 4
