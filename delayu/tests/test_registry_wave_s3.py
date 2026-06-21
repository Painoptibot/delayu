"""#9, #31, #34, #37, #42 — волна S3."""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from delayu.models import (
    AiHumanReview,
    DataRetentionPolicy,
    DocumentFile,
    IntegrationEndpoint,
    IntegrationMessage,
    Organization,
    ReportSchedule,
    ReportTemplate,
    SignatureRequest,
)
from delayu.services.integrations import move_to_dead_letter, process_pending_queue, queue_metrics
from delayu.services.report_schedules import run_schedule, schedule_is_due
from delayu.services.retention import default_archive_years, get_or_create_retention_policy
from delayu.services.signatures import complete_signature, create_signature_request, send_to_signing

User = get_user_model()


@pytest.fixture
def s3_sub(db):
    from delayu.models import CaseFile, ModuleCatalog, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="s3wave", name="S3", industry_template="core")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Spec")
    for code in ["M16", "M17", "M22", "M30", "M42", "M47", "M80"]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": code, "group": "core"})
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_change=True, can_delete=True)
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("s3_user", password="secret")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    return sub, user, org


@pytest.mark.django_db
def test_retention_policy(s3_sub):
    sub, _user, _org = s3_sub
    policy = get_or_create_retention_policy(sub)
    policy.default_archive_years = 7
    policy.save()
    assert default_archive_years(sub) == 7


@pytest.mark.django_db
def test_report_schedule_run(s3_sub):
    sub, user, _org = s3_sub
    tpl = ReportTemplate.objects.create(
        subsystem=sub, code="r1", name="R1", query_key="cases_open", columns=[]
    )
    sched = ReportSchedule.objects.create(
        subsystem=sub, template=tpl, created_by=user, run_hour=0, is_active=True
    )
    run = run_schedule(sched, user=user)
    assert run.template_id == tpl.pk
    sched.refresh_from_db()
    assert sched.last_run_at is not None


@pytest.mark.django_db
def test_schedule_is_due_daily(s3_sub):
    sub, user, _org = s3_sub
    tpl = ReportTemplate.objects.create(
        subsystem=sub, code="r2", name="R2", query_key="cases_open", columns=[]
    )
    sched = ReportSchedule.objects.create(subsystem=sub, template=tpl, run_hour=0)
    now = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
    assert schedule_is_due(sched, now=now) is True


@pytest.mark.django_db
def test_integration_queue_and_dead_letter(s3_sub):
    sub, _user, _org = s3_sub
    ep = IntegrationEndpoint.objects.create(
        subsystem=sub, code="q1", name="Q", endpoint_type="gateway", max_retries=1
    )
    msg = IntegrationMessage.objects.create(
        endpoint=ep,
        direction=IntegrationMessage.Direction.OUT,
        payload={"x": 1},
        status=IntegrationMessage.Status.PENDING,
        retry_count=1,
    )
    move_to_dead_letter(msg)
    msg.refresh_from_db()
    assert msg.status == IntegrationMessage.Status.DEAD_LETTER
    metrics = queue_metrics(sub)
    assert metrics["dead_letter"] >= 1


@pytest.mark.django_db
def test_signature_request_flow(s3_sub):
    sub, user, org = s3_sub
    from delayu.models import CaseFile

    case = CaseFile.objects.create(subsystem=sub, organization=org, number="S3-1", title="Doc case", created_by=user)
    doc = DocumentFile.objects.create(subsystem=sub, case=case, title="Act", uploaded_by=user, is_current=True)
    req = create_signature_request(document=doc, requester=user)
    send_to_signing(req)
    req.refresh_from_db()
    assert req.status == SignatureRequest.Status.SENT
    complete_signature(req, user=user)
    req.refresh_from_db()
    doc.refresh_from_db()
    assert req.status == SignatureRequest.Status.SIGNED
    assert doc.is_signed is True


@pytest.mark.django_db
def test_ai_hitl_approve(s3_sub):
    sub, user, _org = s3_sub
    from delayu.services.ai_hitl import approve_review, create_review

    review = create_review(subsystem=sub, user=user, title="Test", ai_output="draft")
    approve_review(review, reviewer=user, comment="ok")
    review.refresh_from_db()
    assert review.status == AiHumanReview.Status.APPROVED
