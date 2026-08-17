import pytest
from django.core.management import call_command

from delayu.models import Subsystem, SubsystemModule
from delayu.models_invest import (
    InvestExtract,
    InvestFgistpDocument,
    InvestFgistpRecord,
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
    assert subsystem.invest_sites.count() == 5
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
    assert InvestSite.objects.filter(subsystem=subsystem).count() == 5
    demo_smev = InvestSite.objects.get(subsystem=subsystem, cadastral_number="23:43:0101001:77")
    assert demo_smev.status == InvestSite.Status.DRAFT
    assert demo_smev.completeness_pct < 40
    project = InvestProject.objects.get(subsystem=subsystem, code="P-INV-001")
    assert project.contact_person
    assert project.investment_amount == 1250
    extracts = InvestExtract.objects.filter(subsystem=subsystem)
    assert extracts.count() == 7
    assert set(extracts.values_list("status", flat=True)) == {
        InvestExtract.Status.DRAFT,
        InvestExtract.Status.REQUESTED,
        InvestExtract.Status.RECEIVED,
        InvestExtract.Status.VERIFIED,
        InvestExtract.Status.ATTACHED,
        InvestExtract.Status.REJECTED,
        InvestExtract.Status.EXPIRED,
    }
    fgistp = InvestFgistpRecord.objects.filter(subsystem=subsystem)
    assert fgistp.count() == 7
    assert set(fgistp.values_list("status", flat=True)) == {
        InvestFgistpRecord.Status.DRAFT,
        InvestFgistpRecord.Status.REQUESTED,
        InvestFgistpRecord.Status.RECEIVED,
        InvestFgistpRecord.Status.VERIFIED,
        InvestFgistpRecord.Status.ATTACHED,
        InvestFgistpRecord.Status.REJECTED,
        InvestFgistpRecord.Status.EXPIRED,
    }
    assert InvestFgistpDocument.objects.filter(subsystem=subsystem, is_active=True).count() >= 6
    assert InvestFgistpDocument.objects.filter(
        subsystem=subsystem, cadastral_numbers__contains=["23:43:0107001:101"]
    ).exists() or any(
        "23:43:0107001:101" in (doc.cadastral_numbers or [])
        for doc in InvestFgistpDocument.objects.filter(subsystem=subsystem)
    )
