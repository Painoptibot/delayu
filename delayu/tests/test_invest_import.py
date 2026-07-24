import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from delayu.models import Organization, Subsystem
from delayu.models_invest import InvestImportRow, InvestProject, InvestSite
from delayu.services.invest_import import apply_row, parse_mo_file, skip_row

User = get_user_model()


@pytest.fixture
def invest_ctx(db):
    sub = Subsystem.objects.create(code="inv-i", name="I", industry_template="invest", status="active")
    org = Organization.objects.create(subsystem=sub, code="mo1", name="МО-1")
    user = User.objects.create_user("inv_imp", password="x")
    return {"sub": sub, "org": org, "user": user}


@pytest.mark.django_db
def test_import_apply_creates_project(invest_ctx):
    content = b"code,name,stage\nP-IMP,Imported,lead\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get()
    assert row.action == InvestImportRow.Action.NEW_PROJECT
    obj = apply_row(row, user=invest_ctx["user"])
    assert obj.code == "P-IMP"
    row.refresh_from_db()
    assert row.resolution == InvestImportRow.Resolution.APPLIED


@pytest.mark.django_db
def test_import_changed_project_requires_apply(invest_ctx):
    InvestProject.objects.create(
        subsystem=invest_ctx["sub"], code="P-1", name="Проект 1",
        organization=invest_ctx["org"], funnel="attraction", stage="site_pick",
    )
    content = b"code,name,stage\nP-1,Updated Name,lead\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get(action=InvestImportRow.Action.CHANGED_PROJECT)
    project = InvestProject.objects.get(code="P-1")
    assert project.name == "Проект 1"
    apply_row(row, user=invest_ctx["user"])
    project.refresh_from_db()
    assert project.name == "Updated Name"


@pytest.mark.django_db
def test_import_skip_row(invest_ctx):
    content = b"code,name,stage\nP-IMP,Imported,lead\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get()
    skip_row(row)
    row.refresh_from_db()
    assert row.resolution == InvestImportRow.Resolution.SKIPPED
    assert not InvestProject.objects.filter(code="P-IMP").exists()


@pytest.mark.django_db
def test_import_new_site(invest_ctx):
    content = b"code,name,cadastral_number,stage\n,S-NEW,23:00:0000000:99,actual\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get()
    assert row.action == InvestImportRow.Action.NEW_SITE
    obj = apply_row(row, user=invest_ctx["user"])
    assert obj.cadastral_number == "23:00:0000000:99"


@pytest.mark.django_db
def test_import_gap_apply_rejected(invest_ctx):
    project = InvestProject.objects.create(
        subsystem=invest_ctx["sub"], code="P-GAP", name="Missing",
        organization=invest_ctx["org"], funnel="attraction", stage="site_pick",
    )
    content = b"code,name,stage\nP-OTHER,Other,lead\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get(action=InvestImportRow.Action.GAP)
    assert row.target_project_id == project.id

    with pytest.raises(ValueError, match="gap"):
        apply_row(row, user=invest_ctx["user"])

    project.refresh_from_db()
    assert project.name == "Missing"
    row.refresh_from_db()
    assert row.resolution == InvestImportRow.Resolution.PENDING


@pytest.mark.django_db
def test_import_changed_site_requires_apply(invest_ctx):
    site = InvestSite.objects.create(
        subsystem=invest_ctx["sub"],
        organization=invest_ctx["org"],
        cadastral_number="23:00:0000000:11",
        name="Old Name",
        status=InvestSite.Status.DRAFT,
    )
    content = b"code,name,cadastral_number,stage\n,S-UPD,23:00:0000000:11,actual\n"
    f = SimpleUploadedFile("mo.csv", content, content_type="text/csv")
    batch = parse_mo_file(f, subsystem=invest_ctx["sub"], organization=invest_ctx["org"])
    row = batch.rows.get(action=InvestImportRow.Action.CHANGED_SITE)
    site.refresh_from_db()
    assert site.name == "Old Name"
    assert site.status == InvestSite.Status.DRAFT

    apply_row(row, user=invest_ctx["user"])
    site.refresh_from_db()
    assert site.name == "S-UPD"
    assert site.status == InvestSite.Status.ACTUAL
