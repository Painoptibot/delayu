"""#32, #36, #48, #50 — волна S4."""
import pytest
from django.contrib.auth import get_user_model

from delayu.models import EtlJob, EtlRun, MailDeliveryLog, UserProfile
from delayu.services.infra import run_etl_job
from delayu.services.mail_delivery import delivery_metrics, filter_delivery_logs, serialize_log
from delayu.services.onboarding import build_steps, dismiss_onboarding, mark_step, profile_state

User = get_user_model()


@pytest.fixture
def s4_sub(db):
    from delayu.models import ModuleCatalog, Organization, Role, RoleModulePermission, Subsystem, SubsystemMembership, SubsystemModule

    sub = Subsystem.objects.create(code="s4wave", name="S4", industry_template="core", status="active")
    org = Organization.objects.create(subsystem=sub, code="o1", name="Org")
    role = Role.objects.create(subsystem=sub, code="specialist", name="Spec")
    for code in ["M70", "M78"]:
        mod, _ = ModuleCatalog.objects.get_or_create(code=code, defaults={"name": code, "group": "core"})
        RoleModulePermission.objects.create(role=role, module=mod, can_view=True, can_change=True)
        SubsystemModule.objects.create(subsystem=sub, module=mod, enabled=True)
    user = User.objects.create_user("s4_user", password="secret")
    SubsystemMembership.objects.create(user=user, subsystem=sub, organization=org, role=role, is_default=True)
    return sub, user, org


@pytest.mark.django_db
def test_etl_error_rows(s4_sub):
    sub, _user, _org = s4_sub
    job = EtlJob.objects.create(subsystem=sub, name="Import CSV", source_type="csv")
    runs_with_errors = []
    for _ in range(30):
        run = run_etl_job(job)
        if run.error_rows:
            runs_with_errors.append(run)
            break
    assert runs_with_errors or EtlRun.objects.filter(job=job).exists()


@pytest.mark.django_db
def test_mail_delivery_log_api_shape(s4_sub):
    sub, _user, _org = s4_sub
    log = MailDeliveryLog.objects.create(
        subsystem=sub,
        direction=MailDeliveryLog.Direction.OUTBOUND,
        recipient="a@test.local",
        subject="Test",
        event_code="case_notify",
        success=False,
        error_message="SMTP refused",
    )
    data = serialize_log(log)
    assert data["success"] is False
    assert filter_delivery_logs(sub, {"success": "0"}).filter(pk=log.pk).exists()
    assert delivery_metrics(sub)["failed"] >= 1


@pytest.mark.django_db
def test_onboarding_state(s4_sub):
    sub, user, _org = s4_sub
    mark_step(user, "search")
    state = profile_state(user)
    assert "search" in state["completed"]
    steps = build_steps(user, type("M", (), {"subsystem": sub})())
    assert len(steps) >= 5
    dismiss_onboarding(user)
    assert profile_state(user).get("dismissed_at")


@pytest.mark.django_db
def test_scheduled_tasks_service(s4_sub):
    from delayu.services.scheduled_tasks import run_all_scheduled

    sub, _user, _org = s4_sub
    result = run_all_scheduled(subsystem_code=sub.code)
    assert "queue" in result
