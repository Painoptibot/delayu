from datetime import date, timedelta
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from delayu.models import Subsystem
from delayu.models_uzhv import (
    HousingAdminProtocol,
    HousingAppeal,
    HousingCitizen,
    HousingContract,
    HousingInspection,
    HousingPrescription,
    HousingQueueCase,
    MunicipalBuilding,
    MunicipalPremise,
)
from delayu.services.uzhv_bulk import (
    bulk_close_contracts,
    bulk_set_appeal_status,
    bulk_set_case_status,
    bulk_set_prescription_status,
    bulk_set_young_family_meets_criteria,
    export_admin_protocols_csv,
    export_appeals_csv,
    export_cases_csv,
    export_contracts_csv,
)
from delayu.services.uzhv_search import parse_uzhv_search_query, uzhv_global_search
from delayu.services.uzhv_timeline import (
    build_building_timeline,
    build_case_timeline,
    build_citizen_timeline,
)

User = get_user_model()


@pytest.fixture
def uzhv_subsystem(db):
    return Subsystem.objects.create(
        code="uzhv_test",
        name="УЖВ тест",
        industry_template="uzhv",
    )


@pytest.fixture
def uzhv_user(db):
    return User.objects.create_user("uzhv_tester", password="test")


@pytest.fixture
def uzhv_citizen(uzhv_subsystem):
    return HousingCitizen.objects.create(
        subsystem=uzhv_subsystem,
        last_name="Иванов",
        first_name="Иван",
        middle_name="Иванович",
    )


@pytest.fixture
def uzhv_case(uzhv_subsystem, uzhv_citizen):
    return HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        case_number="УЖВ-2026-001",
        status=HousingQueueCase.Status.REGISTERED,
        registered_at=date(2026, 1, 10),
    )


@pytest.fixture
def uzhv_appeal(uzhv_subsystem, uzhv_citizen, uzhv_case, uzhv_user):
    today = timezone.now().date()
    return HousingAppeal.objects.create(
        subsystem=uzhv_subsystem,
        appeal_number="ОБР-2026-007",
        received_at=today - timedelta(days=10),
        due_date=today + timedelta(days=3),
        citizen=uzhv_citizen,
        housing_case=uzhv_case,
        subject="Вопрос по очереди",
        created_by=uzhv_user,
    )


def test_parse_uzhv_search_query():
    assert parse_uzhv_search_query("обращение:ОБР-2026") == ("uzhv_appeal", "ОБР-2026")
    assert parse_uzhv_search_query("дело:Иванов") == ("uzhv_case", "Иванов")
    assert parse_uzhv_search_query("plain text") == (None, "plain text")


@pytest.mark.django_db
def test_uzhv_global_search_typed(uzhv_subsystem, uzhv_appeal):
    hits = uzhv_global_search(uzhv_subsystem, "обращение:ОБР-2026")
    assert len(hits) == 1
    assert hits[0]["type"] == "uzhv_appeal"
    assert "ОБР-2026" in hits[0]["title"]


@pytest.mark.django_db
def test_uzhv_global_search_case(uzhv_subsystem, uzhv_case):
    hits = uzhv_global_search(uzhv_subsystem, "дело:УЖВ-2026")
    assert any(h["type"] == "uzhv_case" for h in hits)


@pytest.mark.django_db
def test_build_case_timeline(uzhv_case, uzhv_appeal):
    events = build_case_timeline(uzhv_case)
    assert len(events) >= 2
    titles = [e.title for e in events]
    assert any("Постановка на учёт" in t for t in titles)
    assert any("ОБР-2026" in t for t in titles)


@pytest.mark.django_db
def test_export_cases_csv(uzhv_subsystem, uzhv_case):
    resp = export_cases_csv(uzhv_subsystem, [uzhv_case.pk])
    assert resp.status_code == 200
    body = resp.content.decode("utf-8-sig")
    assert "УЖВ-2026-001" in body
    assert "Иванов" in body


@pytest.mark.django_db
def test_bulk_set_case_status(uzhv_subsystem, uzhv_case):
    n = bulk_set_case_status(
        uzhv_subsystem, [uzhv_case.pk], HousingQueueCase.Status.QUEUED
    )
    assert n == 1
    uzhv_case.refresh_from_db()
    assert uzhv_case.status == HousingQueueCase.Status.QUEUED


@pytest.mark.django_db
def test_bulk_set_appeal_status(uzhv_subsystem, uzhv_appeal):
    n = bulk_set_appeal_status(
        uzhv_subsystem, [uzhv_appeal.pk], HousingAppeal.Status.IN_WORK
    )
    assert n == 1
    uzhv_appeal.refresh_from_db()
    assert uzhv_appeal.status == HousingAppeal.Status.IN_WORK

@pytest.mark.django_db
def test_build_citizen_timeline(uzhv_citizen, uzhv_case, uzhv_appeal):
    events = build_citizen_timeline(uzhv_citizen)
    assert len(events) >= 3
    titles = " ".join(e.title for e in events)
    assert "УЖВ-2026" in titles
    assert "ОБР-2026" in titles


@pytest.mark.django_db
def test_parse_search_inspection_prefix():
    assert parse_uzhv_search_query("проверка:123") == ("uzhv_inspection", "123")


@pytest.mark.django_db
def test_bulk_set_case_assignee(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.models import Organization, Role, SubsystemMembership
    from delayu.services.uzhv_bulk import bulk_set_case_assignee

    org = Organization.objects.create(subsystem=uzhv_subsystem, code="o1", name="Org")
    role = Role.objects.create(subsystem=uzhv_subsystem, code="r1", name="Role")
    SubsystemMembership.objects.create(
        user=uzhv_user, subsystem=uzhv_subsystem, organization=org, role=role
    )
    n = bulk_set_case_assignee(uzhv_subsystem, [uzhv_case.pk], uzhv_user.pk)
    assert n == 1
    uzhv_case.refresh_from_db()
    assert uzhv_case.assignee_id == uzhv_user.pk


@pytest.fixture
def uzhv_building(uzhv_subsystem):
    return MunicipalBuilding.objects.create(
        subsystem=uzhv_subsystem,
        address="ул. Красная, 1",
        condition=MunicipalBuilding.Condition.OK,
    )


@pytest.fixture
def uzhv_contract(uzhv_subsystem, uzhv_citizen, uzhv_building):
    premise = MunicipalPremise.objects.create(
        building=uzhv_building,
        number="12",
        status=MunicipalPremise.Status.OCCUPIED,
    )
    return HousingContract.objects.create(
        subsystem=uzhv_subsystem,
        contract_number="ДГ-2026-001",
        contract_type=HousingContract.ContractType.SOCIAL,
        citizen=uzhv_citizen,
        premise=premise,
        signed_at=date(2026, 3, 1),
        is_active=True,
    )


@pytest.mark.django_db
def test_build_building_timeline(uzhv_building, uzhv_contract):
    events = build_building_timeline(uzhv_building)
    assert len(events) >= 2
    titles = " ".join(e.title for e in events)
    assert "ДГ-2026" in titles


@pytest.mark.django_db
def test_bulk_close_contracts(uzhv_subsystem, uzhv_contract):
    n = bulk_close_contracts(uzhv_subsystem, [uzhv_contract.pk])
    assert n == 1
    uzhv_contract.refresh_from_db()
    assert uzhv_contract.is_active is False


@pytest.mark.django_db
def test_export_contracts_csv(uzhv_subsystem, uzhv_contract):
    resp = export_contracts_csv(uzhv_subsystem, [uzhv_contract.pk])
    body = resp.content.decode("utf-8-sig")
    assert "ДГ-2026-001" in body


@pytest.mark.django_db
def test_parse_search_contract_prefix():
    assert parse_uzhv_search_query("договор:ДГ") == ("uzhv_contract", "ДГ")


@pytest.mark.django_db
def test_export_appeals_csv(uzhv_subsystem, uzhv_appeal):
    resp = export_appeals_csv(uzhv_subsystem, [uzhv_appeal.pk])
    body = resp.content.decode("utf-8-sig")
    assert "ОБР-2026-007" in body


@pytest.mark.django_db
def test_upcoming_deadlines(uzhv_subsystem, uzhv_appeal):
    from delayu.services.uzhv_deadlines import upcoming_deadlines

    items = upcoming_deadlines(uzhv_subsystem, days=30)
    assert any(i.kind == "appeal" for i in items)


@pytest.mark.django_db
def test_bulk_set_court_case_status(uzhv_subsystem):
    from delayu.models_uzhv import HousingCourtCase
    from delayu.services.uzhv_bulk import bulk_set_court_case_status

    court = HousingCourtCase.objects.create(
        subsystem=uzhv_subsystem,
        court_name="Краснодарский суд",
        case_number="СУД-2026-001",
        status=HousingCourtCase.Status.OPEN,
    )
    n = bulk_set_court_case_status(
        uzhv_subsystem, [court.pk], HousingCourtCase.Status.HEARING
    )
    assert n == 1
    court.refresh_from_db()
    assert court.status == HousingCourtCase.Status.HEARING


@pytest.mark.django_db
def test_export_citizens_csv_masks_pii(uzhv_subsystem, uzhv_citizen):
    from delayu.services.uzhv_bulk import export_citizens_csv

    resp = export_citizens_csv(uzhv_subsystem, [uzhv_citizen.pk], user=None)
    body = resp.content.decode("utf-8-sig")
    assert "Иванов" not in body or "•" in body


@pytest.mark.django_db
def test_deadlines_grouped(uzhv_subsystem, uzhv_appeal):
    from delayu.services.uzhv_deadlines import deadlines_grouped

    groups = deadlines_grouped(uzhv_subsystem, days=14)
    assert len(groups) == 14
    total = sum(len(items) for _, items in groups)
    assert total >= 1

@pytest.mark.django_db
def test_export_deadlines_ical(uzhv_subsystem, uzhv_appeal):
    from delayu.services.uzhv_deadlines import export_deadlines_ical

    resp = export_deadlines_ical(uzhv_subsystem, days=30)
    body = resp.content.decode("utf-8")
    assert "BEGIN:VCALENDAR" in body
    assert "VEVENT" in body


@pytest.mark.django_db
def test_sync_uzhv_notifications(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.models import Notification
    from delayu.services.uzhv_notifications import sync_uzhv_deadline_notifications

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.due_date = timezone.now().date() - timedelta(days=1)
    uzhv_appeal.save()
    result = sync_uzhv_deadline_notifications(uzhv_subsystem)
    assert result["created"] >= 1
    assert "push_sent" in result
    assert Notification.objects.filter(user=uzhv_user, subsystem=uzhv_subsystem).exists()


@pytest.mark.django_db
def test_export_deadlines_csv(uzhv_subsystem, uzhv_appeal):
    from delayu.services.uzhv_deadlines import export_deadlines_csv

    resp = export_deadlines_csv(uzhv_subsystem, days=30)
    body = resp.content.decode("utf-8-sig")
    assert "ОБР-2026" in body or "Обращение" in body


@pytest.mark.django_db
def test_export_admin_protocols_csv(uzhv_subsystem):
    insp = HousingInspection.objects.create(
        subsystem=uzhv_subsystem,
        inspection_number="ПР-TEST-01",
    )
    p = HousingAdminProtocol.objects.create(
        inspection=insp,
        protocol_number="ПРТ-TEST-01",
        legal_article="12.1",
        violator_name="ООО Тест",
    )
    resp = export_admin_protocols_csv(uzhv_subsystem, [p.pk])
    body = resp.content.decode("utf-8-sig")
    assert "ПРТ-TEST-01" in body


@pytest.mark.django_db
def test_deadlines_for_month(uzhv_subsystem, uzhv_appeal):
    from delayu.services.uzhv_deadlines import deadlines_for_month

    today = timezone.now().date()
    events = deadlines_for_month(uzhv_subsystem, today.replace(day=1))
    assert isinstance(events, list)


@pytest.mark.django_db
def test_build_assignee_workload(uzhv_subsystem, uzhv_appeal, uzhv_user, uzhv_case):
    from delayu.services.uzhv_workload import build_assignee_workload

    uzhv_case.assignee = uzhv_user
    uzhv_case.save()
    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.save()
    rows = build_assignee_workload(uzhv_subsystem)
    assert any(r["name"] and r["appeals_open"] >= 1 for r in rows)


@pytest.mark.django_db
def test_uzhv_user_alerts(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.services.uzhv_pwa import uzhv_user_alerts

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.due_date = timezone.now().date() - timedelta(days=1)
    uzhv_appeal.save()
    data = uzhv_user_alerts(uzhv_subsystem, uzhv_user)
    assert data["overdue_count"] >= 1
    assert data["has_alerts"] is True


@pytest.mark.django_db
def test_telegram_chat_id_preferred(uzhv_subsystem, uzhv_user):
    from delayu.models import UserProfile
    from delayu.services.notify_dispatch import _user_telegram

    UserProfile.objects.update_or_create(
        user=uzhv_user,
        defaults={"telegram": "@name", "telegram_chat_id": "123456789"},
    )
    assert _user_telegram(uzhv_user) == "123456789"


@pytest.mark.django_db
def test_normalize_telegram_chat_id():
    from delayu.services.telegram import normalize_telegram_chat_id

    assert normalize_telegram_chat_id("123456789") == "123456789"
    assert normalize_telegram_chat_id("@user") == "@user"
    assert normalize_telegram_chat_id("user") == "@user"


@pytest.mark.django_db
def test_report_workload_assignees(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.services.uzhv_reports import report_workload_assignees

    uzhv_case.assignee = uzhv_user
    uzhv_case.save()
    body = report_workload_assignees(uzhv_subsystem)
    assert "Исполнитель" in body


@pytest.mark.django_db
def test_export_overdue_xlsx(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.services.uzhv_overdue import export_overdue_xlsx

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.due_date = timezone.now().date() - timedelta(days=1)
    uzhv_appeal.save()
    resp = export_overdue_xlsx(uzhv_subsystem)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]
    assert resp.content[:2] == b"PK"


@pytest.mark.django_db
def test_interagency_responsible_label(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.models_uzhv import HousingInteragencyRequest

    uzhv_case.assignee = uzhv_user
    uzhv_case.save()
    req = HousingInteragencyRequest.objects.create(
        subsystem=uzhv_subsystem,
        request_number="МВ-TEST-01",
        recipient_name="Росреестр",
        subject="Тест",
        housing_case=uzhv_case,
        due_date=timezone.now().date() + timedelta(days=5),
        created_by=uzhv_user,
    )
    assert req.responsible_label == uzhv_user.get_full_name() or uzhv_user.username


@pytest.mark.django_db
def test_send_telegram_demo_token_fallback(uzhv_subsystem):
    from delayu.models import MessengerChannel
    from delayu.services.telegram import send_telegram_message

    MessengerChannel.objects.create(
        subsystem=uzhv_subsystem,
        code="tg",
        name="TG",
        channel_type=MessengerChannel.ChannelType.TELEGRAM,
        webhook_url="https://api.telegram.org/bot/demo/webhook",
        is_active=True,
    )
    assert send_telegram_message(uzhv_subsystem, "@testuser", "Hello") is False


@pytest.mark.django_db
def test_export_overdue_csv(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.services.uzhv_overdue import export_overdue_csv

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.due_date = timezone.now().date() - timedelta(days=1)
    uzhv_appeal.save()
    resp = export_overdue_csv(uzhv_subsystem)
    body = resp.content.decode("utf-8-sig")
    assert "Обращение" in body
    assert "ОБР-2026" in body


@pytest.mark.django_db
def test_telegram_preferred_over_sms(uzhv_subsystem, uzhv_user):
    from delayu.models import MailDeliveryLog, UserProfile
    from delayu.services.notify_dispatch import _send_sms_template

    UserProfile.objects.update_or_create(
        user=uzhv_user,
        defaults={"phone_mobile": "+79990001122", "telegram": "@uzhv_spec"},
    )
    _send_sms_template(
        uzhv_user,
        uzhv_subsystem,
        subject="Тест",
        body="Просрочка",
        event_code="uzhv_deadline_urgent",
    )
    log = MailDeliveryLog.objects.filter(subsystem=uzhv_subsystem).latest("created_at")
    assert log.recipient.startswith("telegram:")


@pytest.mark.django_db
def test_bulk_set_young_family_program(uzhv_subsystem, uzhv_case):
    from delayu.models_uzhv import YoungFamilyRecord
    from delayu.services.uzhv_bulk import bulk_set_young_family_program

    YoungFamilyRecord.objects.create(
        case=uzhv_case, program=YoungFamilyRecord.Program.JSK
    )
    n = bulk_set_young_family_program(
        uzhv_subsystem, [uzhv_case.pk], YoungFamilyRecord.Program.ECONOMY
    )
    assert n == 1
    assert (
        YoungFamilyRecord.objects.get(case=uzhv_case).program
        == YoungFamilyRecord.Program.ECONOMY
    )


@pytest.mark.django_db
def test_list_overdue_items(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.services.uzhv_overdue import list_overdue_items

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.due_date = timezone.now().date() - timedelta(days=2)
    uzhv_appeal.save()
    all_items = list_overdue_items(uzhv_subsystem)
    assert len(all_items) >= 1
    mine = list_overdue_items(uzhv_subsystem, assignee_id=uzhv_user.pk)
    assert all(i.kind == "appeal" for i in mine)
    assert len(mine) >= 1


@pytest.mark.django_db
def test_bulk_set_young_family_meets_criteria(uzhv_subsystem, uzhv_case):
    from delayu.models_uzhv import YoungFamilyRecord
    from delayu.services.uzhv_bulk import bulk_set_young_family_meets_criteria

    YoungFamilyRecord.objects.create(case=uzhv_case, meets_criteria=False)
    n = bulk_set_young_family_meets_criteria(uzhv_subsystem, [uzhv_case.pk], meets=True)
    assert n == 1
    assert YoungFamilyRecord.objects.get(case=uzhv_case).meets_criteria is True


@pytest.mark.django_db
def test_export_young_families_csv(uzhv_subsystem, uzhv_case):
    from delayu.models_uzhv import YoungFamilyRecord
    from delayu.services.uzhv_bulk import export_young_families_csv

    uzhv_case.category = HousingQueueCase.Category.YOUNG_FAMILY
    uzhv_case.save()
    YoungFamilyRecord.objects.create(case=uzhv_case, children_count=1)
    resp = export_young_families_csv(uzhv_subsystem, [uzhv_case.pk])
    body = resp.content.decode("utf-8-sig")
    assert "УЖВ-2026" in body


@pytest.mark.django_db
def test_bulk_set_orphan_housing_status(uzhv_subsystem, uzhv_case):
    from delayu.models_uzhv import OrphanHousingRecord
    from delayu.services.uzhv_bulk import bulk_set_orphan_housing_status

    uzhv_case.category = HousingQueueCase.Category.ORPHAN
    uzhv_case.save()
    OrphanHousingRecord.objects.create(case=uzhv_case)
    n = bulk_set_orphan_housing_status(
        uzhv_subsystem,
        [uzhv_case.pk],
        OrphanHousingRecord.HousingStatus.IN_LIST,
    )
    assert n == 1
    rec = OrphanHousingRecord.objects.get(case=uzhv_case)
    assert rec.housing_status == OrphanHousingRecord.HousingStatus.IN_LIST


@pytest.fixture
def uzhv_membership(uzhv_subsystem, uzhv_user):
    from delayu.models import (
        ModuleCatalog,
        Organization,
        Role,
        RoleModulePermission,
        SubsystemMembership,
        SubsystemModule,
    )

    org = Organization.objects.create(subsystem=uzhv_subsystem, code="o1", name="Org")
    role = Role.objects.create(subsystem=uzhv_subsystem, code="spec", name="Spec")
    mod22, _ = ModuleCatalog.objects.get_or_create(
        code="M22", defaults={"name": "АИС УЖВ", "group": "ops"}
    )
    mod07, _ = ModuleCatalog.objects.get_or_create(
        code="M07", defaults={"name": "Кабинет", "group": "workplace"}
    )
    RoleModulePermission.objects.create(
        role=role, module=mod22, can_view=True, can_create=True, can_change=True
    )
    RoleModulePermission.objects.create(role=role, module=mod07, can_view=True)
    SubsystemModule.objects.create(subsystem=uzhv_subsystem, module=mod22, enabled=True)
    SubsystemModule.objects.create(subsystem=uzhv_subsystem, module=mod07, enabled=True)
    return SubsystemMembership.objects.create(
        user=uzhv_user,
        subsystem=uzhv_subsystem,
        organization=org,
        role=role,
        is_default=True,
    )


@pytest.mark.django_db
def test_build_assignee_workload_includes_user_id(
    uzhv_subsystem, uzhv_appeal, uzhv_user, uzhv_case
):
    from delayu.services.uzhv_workload import build_assignee_workload

    uzhv_case.assignee = uzhv_user
    uzhv_case.save()
    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.save()
    rows = build_assignee_workload(uzhv_subsystem)
    match = [r for r in rows if r["user_id"] == uzhv_user.pk]
    assert len(match) == 1
    assert match[0]["appeals_open"] >= 1


@pytest.mark.django_db
def test_assignee_workload_row(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.services.uzhv_workload import assignee_workload_row

    uzhv_appeal.assignee = uzhv_user
    uzhv_appeal.save()
    row = assignee_workload_row(uzhv_subsystem, uzhv_user.pk)
    assert row["user_id"] == uzhv_user.pk
    assert row["appeals_open"] >= 1


@pytest.mark.django_db
def test_export_workload_xlsx(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.services.uzhv_workload import export_workload_xlsx

    uzhv_case.assignee = uzhv_user
    uzhv_case.save()
    resp = export_workload_xlsx(uzhv_subsystem)
    assert resp.status_code == 200
    assert "spreadsheetml" in resp["Content-Type"]
    assert resp.content[:2] == b"PK"


@pytest.mark.django_db
def test_save_and_clear_push_subscription(uzhv_user):
    from delayu.models import UserProfile
    from delayu.services.uzhv_pwa import clear_push_subscription, save_push_subscription

    payload = {
        "endpoint": "https://push.example/sub/1",
        "keys": {"p256dh": "abc", "auth": "def"},
    }
    assert save_push_subscription(uzhv_user, payload) is True
    profile = UserProfile.objects.get(user=uzhv_user)
    assert profile.uzhv_push_subscription["endpoint"] == payload["endpoint"]
    clear_push_subscription(uzhv_user)
    profile.refresh_from_db()
    assert profile.uzhv_push_subscription == {}


@pytest.mark.django_db
def test_send_uzhv_web_push_without_keys(uzhv_user):
    from delayu.models import UserProfile
    from delayu.services.uzhv_webpush import send_uzhv_web_push

    UserProfile.objects.update_or_create(
        user=uzhv_user,
        defaults={
            "uzhv_push_subscription": {
                "endpoint": "https://push.example/sub/1",
                "keys": {"p256dh": "x", "auth": "y"},
            }
        },
    )
    assert send_uzhv_web_push(uzhv_user, title="T", body="B", url="/uzhv/") is False


@pytest.mark.django_db
def test_uzhv_service_worker_view(client):
    resp = client.get(reverse("uzhv-service-worker"))
    assert resp.status_code == 200
    assert "javascript" in resp["Content-Type"]
    assert "push" in resp.content.decode("utf-8")


@pytest.mark.django_db
def test_uzhv_push_subscribe_view(client, uzhv_membership, uzhv_user):
    client.force_login(uzhv_user)
    payload = {
        "endpoint": "https://push.example/sub/42",
        "keys": {"p256dh": "k1", "auth": "k2"},
    }
    resp = client.post(
        reverse("uzhv-push-subscribe"),
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.django_db
def test_push_subscription_status(uzhv_user):
    from delayu.models import UserProfile
    from delayu.services.uzhv_pwa import push_subscription_status

    status = push_subscription_status(uzhv_user)
    assert status["subscribed"] is False
    UserProfile.objects.update_or_create(
        user=uzhv_user,
        defaults={
            "uzhv_push_subscription": {"endpoint": "https://push.example/x", "keys": {}}
        },
    )
    status = push_subscription_status(uzhv_user)
    assert status["subscribed"] is True
    assert "push.example" in status["endpoint_preview"]


@pytest.mark.django_db
def test_user_has_uzhv_membership(uzhv_subsystem, uzhv_user, uzhv_membership):
    from delayu.services.uzhv_pwa import user_has_uzhv_membership

    assert user_has_uzhv_membership(uzhv_user) is True


@pytest.mark.django_db
def test_cabinet_uzhv_push_view(client, uzhv_membership, uzhv_user):
    client.force_login(uzhv_user)
    payload = {
        "endpoint": "https://push.example/cabinet",
        "keys": {"p256dh": "a", "auth": "b"},
    }
    resp = client.post(
        reverse("platform-cabinet-uzhv-push"),
        data=json.dumps(payload),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


@pytest.mark.django_db
def test_validate_snils_ok_and_bad():
    from delayu.services.uzhv_validation import validate_snils

    ok, _ = validate_snils("112-233-445 95")
    assert ok is True
    ok, msg = validate_snils("112-233-445 00")
    assert ok is False
    assert "контроль" in msg.lower() or "сумм" in msg.lower()


@pytest.mark.django_db
def test_recalculate_housing_queue(uzhv_subsystem, uzhv_citizen):
    from delayu.models_uzhv import HousingCitizen, HousingQueueCase
    from delayu.services.uzhv_queue import recalculate_housing_queue

    HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        case_number="Q-1",
        category=HousingQueueCase.Category.GENERAL,
        status=HousingQueueCase.Status.REGISTERED,
        registered_at=date(2026, 1, 1),
    )
    c2 = HousingCitizen.objects.create(
        subsystem=uzhv_subsystem, last_name="Петров", first_name="Пётр"
    )
    HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=c2,
        case_number="Q-2",
        category=HousingQueueCase.Category.ORPHAN,
        status=HousingQueueCase.Status.REGISTERED,
        registered_at=date(2026, 2, 1),
    )
    result = recalculate_housing_queue(uzhv_subsystem)
    assert result.total == 2
    assert result.updated == 2
    orphan = HousingQueueCase.objects.get(case_number="Q-2")
    general = HousingQueueCase.objects.get(case_number="Q-1")
    assert orphan.queue_position == 1
    assert general.queue_position == 2
    assert orphan.status == HousingQueueCase.Status.QUEUED


@pytest.mark.django_db
def test_recalculate_clears_removed_queue_position(uzhv_subsystem, uzhv_case):
    from delayu.services.uzhv_queue import recalculate_housing_queue

    uzhv_case.status = HousingQueueCase.Status.REGISTERED
    uzhv_case.queue_position = 5
    uzhv_case.save(update_fields=["status", "queue_position"])
    uzhv_case.status = HousingQueueCase.Status.REMOVED
    uzhv_case.save(update_fields=["status"])
    recalculate_housing_queue(uzhv_subsystem)
    uzhv_case.refresh_from_db()
    assert uzhv_case.queue_position is None


@pytest.mark.django_db
def test_auto_recalc_on_case_create(uzhv_subsystem, uzhv_citizen):
    from delayu.models_uzhv import HousingQueueCase

    case = HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        case_number="AUTO-Q-1",
        status=HousingQueueCase.Status.REGISTERED,
        registered_at=date(2026, 1, 15),
    )
    from delayu.services.uzhv_queue import recalculate_housing_queue

    recalculate_housing_queue(uzhv_subsystem)
    case.refresh_from_db()
    assert case.queue_position is not None
    assert case.status == HousingQueueCase.Status.QUEUED


@pytest.mark.django_db
def test_apply_low_income_calculation(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.services.uzhv_low_income_decision import apply_low_income_calculation

    result = apply_low_income_calculation(
        uzhv_case,
        subsystem=uzhv_subsystem,
        monthly_income=10000,
        household_size=3,
        property_value=50000,
        user=uzhv_user,
    )
    uzhv_case.refresh_from_db()
    assert result["eligible"] is True
    assert uzhv_case.category == HousingQueueCase.Category.LOW_INCOME
    assert uzhv_case.queue_position is not None


@pytest.mark.django_db
def test_sync_applicant_to_household(uzhv_subsystem, uzhv_case):
    from delayu.services.uzhv_low_income_decision import sync_applicant_to_household

    member = sync_applicant_to_household(uzhv_case)
    assert member.relation == "applicant"
    assert member.full_name == uzhv_case.citizen.full_name
    assert uzhv_case.household_members.filter(pk=member.pk).exists()


@pytest.mark.django_db
def test_import_fund_csv(uzhv_subsystem):
    from delayu.services.uzhv_fund_import import import_fund_csv
    from delayu.models_uzhv import MunicipalPremise

    csv_text = (
        "address;premise_number;area_sqm;rooms;status\n"
        "ул. Тестовая, 1;10;45.5;2;free\n"
    )
    result = import_fund_csv(uzhv_subsystem, csv_text)
    assert not result.errors
    assert result.premises_created == 1
    assert MunicipalPremise.objects.filter(building__address="ул. Тестовая, 1", number="10").exists()


@pytest.mark.django_db
def test_build_case_zip(uzhv_case):
    import zipfile
    import io

    from delayu.services.uzhv_case_package import build_case_zip_bytes

    data = build_case_zip_bytes(uzhv_case)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "manifest.json" in names
        assert "summary.txt" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["case_number"] == uzhv_case.case_number


@pytest.mark.django_db
def test_save_housing_contract_premise_status(uzhv_subsystem, uzhv_citizen):
    from delayu.models_uzhv import MunicipalBuilding, MunicipalPremise
    from delayu.services.uzhv_contracts import save_housing_contract

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Договорная, 1")
    p = MunicipalPremise.objects.create(building=b, number="1", status=MunicipalPremise.Status.FREE)
    c = HousingContract.objects.create(
        subsystem=uzhv_subsystem,
        contract_number="T-1",
        contract_type=HousingContract.ContractType.SOCIAL,
        citizen=uzhv_citizen,
        premise=p,
        is_active=True,
    )
    save_housing_contract(c)
    p.refresh_from_db()
    assert p.status == MunicipalPremise.Status.OCCUPIED
    c.is_active = False
    c.termination_reason = "Выселение"
    save_housing_contract(c)
    p.refresh_from_db()
    assert p.status == MunicipalPremise.Status.FREE


@pytest.mark.django_db
def test_render_case_document(uzhv_subsystem, uzhv_case):
    from delayu.services.uzhv_documents import render_case_document, seed_uzhv_print_templates

    seed_uzhv_print_templates(uzhv_subsystem)
    uzhv_case.low_income_conclusion = "Тестовое заключение"
    uzhv_case.save()
    title, text = render_case_document(uzhv_case, "uzhv_low_income_conclusion")
    assert title
    assert uzhv_case.case_number in text
    assert "Тестовое заключение" in text


@pytest.mark.django_db
def test_compute_low_income_review_due(uzhv_subsystem):
    from delayu.services.uzhv_low_income import compute_low_income_review_due
    from delayu.services.uzhv_nsi import seed_uzhv_nsi_classifiers

    seed_uzhv_nsi_classifiers(uzhv_subsystem)
    due = compute_low_income_review_due(date(2026, 1, 1), uzhv_subsystem)
    assert due == date(2026, 1, 31)


@pytest.mark.django_db
def test_low_income_deadline_in_calendar(uzhv_subsystem, uzhv_case):
    from delayu.services.uzhv_deadlines import upcoming_deadlines

    uzhv_case.low_income_application_at = date(2026, 1, 1)
    uzhv_case.low_income_review_due_at = timezone.now().date() + timedelta(days=5)
    uzhv_case.low_income_eligible = None
    uzhv_case.save()
    items = upcoming_deadlines(uzhv_subsystem, days=30)
    assert any(i.kind == "low_income" and uzhv_case.case_number in i.title for i in items)


@pytest.mark.django_db
def test_build_orphan_package(uzhv_subsystem, uzhv_citizen):
    import io
    import zipfile

    from delayu.models_uzhv import OrphanHousingRecord
    from delayu.services.uzhv_case_package import build_orphan_package_bytes
    from delayu.services.uzhv_documents import seed_uzhv_print_templates

    seed_uzhv_print_templates(uzhv_subsystem)
    case = HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        case_number="УЖВ-ORPH-1",
        category=HousingQueueCase.Category.ORPHAN,
        status=HousingQueueCase.Status.QUEUED,
    )
    OrphanHousingRecord.objects.create(
        case=case,
        mintrud_decision_number="MT-1",
        housing_status=OrphanHousingRecord.HousingStatus.IN_LIST,
    )
    data = build_orphan_package_bytes(case)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        assert "orphan_cover.txt" in names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["orphan"]["mintrud_decision_number"] == "MT-1"


@pytest.mark.django_db
def test_nsi_inspection_subjects(uzhv_subsystem):
    from delayu.services.uzhv_nsi import nsi_value_choices, seed_uzhv_nsi_classifiers

    seed_uzhv_nsi_classifiers(uzhv_subsystem)
    choices = nsi_value_choices(uzhv_subsystem, "uzhv_inspection_subjects")
    assert len(choices) >= 5
    assert any("МКД" in label for _, label in choices)


@pytest.mark.django_db
def test_otch6_form_rows(uzhv_subsystem, uzhv_citizen):
    from datetime import date

    from delayu.models_uzhv import MunicipalBuilding, MunicipalPremise, HousingContract
    from delayu.services.uzhv_report_forms import build_otch6_rows

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Отчётная, 6")
    p = MunicipalPremise.objects.create(building=b, number="1", area_sqm="50", rooms=2)
    HousingContract.objects.create(
        subsystem=uzhv_subsystem,
        contract_number="О6-1",
        contract_type=HousingContract.ContractType.SOCIAL,
        citizen=uzhv_citizen,
        premise=p,
        signed_at=date(2026, 2, 1),
        is_active=True,
    )
    title, rows = build_otch6_rows(uzhv_subsystem, date(2026, 1, 1), date(2026, 3, 31))
    assert "ОТЧ-6" in title
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "№ п/п")
    assert header_idx >= 4
    data = [r for r in rows[header_idx + 1 :] if r and r[0] and str(r[0]).isdigit()]
    assert len(data) == 1
    assert data[0][1] == "ул. Отчётная, 6"
    assert data[0][6] == 1  # поступило за период


@pytest.mark.django_db
def test_otch9_form_rows(uzhv_subsystem):
    from delayu.models_uzhv import MunicipalBuilding
    from delayu.services.uzhv_report_forms import build_otch9_rows

    MunicipalBuilding.objects.create(
        subsystem=uzhv_subsystem,
        address="ул. Аварийная, 9",
        condition=MunicipalBuilding.Condition.EMERGENCY,
        in_resettlement_program=True,
        cadastral_number="23:43:1234567:89",
        year_built=1965,
        floors=5,
        total_area_sqm="1200",
        residents_count=40,
    )
    title, rows = build_otch9_rows(uzhv_subsystem)
    assert "ОТЧ-9" in title
    header_idx = next(i for i, r in enumerate(rows) if r and r[0] == "№ п/п")
    data = [r for r in rows[header_idx + 1 :] if r and str(r[0]).isdigit()]
    assert len(data) == 1
    assert data[0][2] == "23:43:1234567:89"
    assert data[0][9] == "Да"


@pytest.mark.django_db
def test_formatted_xlsx_export(uzhv_subsystem):
    from delayu.services.uzhv_export import build_report_rows, rows_to_formatted_xlsx_bytes

    _, rows = build_report_rows("otch-9", uzhv_subsystem)
    data = rows_to_formatted_xlsx_bytes(rows, "otch-9")
    assert data[:2] == b"PK"


@pytest.mark.django_db
def test_young_family_criteria(uzhv_subsystem, uzhv_citizen):
    from delayu.models_uzhv import YoungFamilyRecord
    from delayu.services.uzhv_young_family import check_young_family_criteria

    case = HousingQueueCase.objects.create(
        subsystem=uzhv_subsystem,
        citizen=uzhv_citizen,
        case_number="YF-1",
        category=HousingQueueCase.Category.YOUNG_FAMILY,
    )
    uzhv_citizen.birth_date = date(1995, 5, 1)
    uzhv_citizen.save()
    record = YoungFamilyRecord.objects.create(
        case=case,
        spouse_last_name="Петрова",
        spouse_first_name="Мария",
        marriage_date=date(2020, 3, 1),
        spouse_birth_date=date(1996, 1, 1),
        children_count=1,
        program=YoungFamilyRecord.Program.ECONOMY,
    )
    result = check_young_family_criteria(record)
    assert result.meets is True


@pytest.mark.django_db
def test_unfit_premises_report(uzhv_subsystem):
    from delayu.models_uzhv import MunicipalBuilding, MunicipalPremise
    from delayu.services.uzhv_reports import report_unfit_premises

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Непригодная, 1")
    MunicipalPremise.objects.create(
        building=b,
        number="2",
        unfit_for_living=True,
        unfit_decision_ref="A-1",
    )
    csv = report_unfit_premises(uzhv_subsystem)
    assert "ул. Непригодная" in csv
    assert "A-1" in csv


@pytest.mark.django_db
def test_case_status_history_on_update(uzhv_subsystem, uzhv_case, uzhv_user):
    from delayu.models_uzhv import HousingCaseStatusHistory
    from delayu.services.uzhv_case_status import record_case_status_change

    record_case_status_change(
        uzhv_case,
        old_status=uzhv_case.status,
        new_status=HousingQueueCase.Status.QUEUED,
        user=uzhv_user,
        comment="Тест",
    )
    uzhv_case.status = HousingQueueCase.Status.QUEUED
    uzhv_case.save()
    hist = HousingCaseStatusHistory.objects.filter(case=uzhv_case).latest("changed_at")
    assert hist.to_status == HousingQueueCase.Status.QUEUED
    assert hist.comment == "Тест"


@pytest.mark.django_db
def test_consent_document_render(uzhv_subsystem, uzhv_citizen, uzhv_user):
    from delayu.models_uzhv import HousingContract, HousingContractConsent
    from delayu.services.uzhv_documents import render_consent_document, seed_uzhv_print_templates

    seed_uzhv_print_templates(uzhv_subsystem)
    contract = HousingContract.objects.create(
        subsystem=uzhv_subsystem,
        contract_number="С-1",
        contract_type=HousingContract.ContractType.SOCIAL,
        citizen=uzhv_citizen,
        signed_at=date(2026, 1, 1),
    )
    consent = HousingContractConsent.objects.create(
        contract=contract,
        consent_type=HousingContractConsent.ConsentType.SUBLET,
        decision=HousingContractConsent.Decision.APPROVED,
        subject="Иванов И.И.",
        created_by=uzhv_user,
    )
    title, text = render_consent_document(consent)
    assert "С-1" in text
    assert "Иванов" in text
    assert "Поднайм" in title or "поднайм" in text.lower()


@pytest.mark.django_db
def test_personal_account_and_extract(uzhv_subsystem, uzhv_citizen, uzhv_user):
    from delayu.models_uzhv import MunicipalBuilding, MunicipalPremise
    from delayu.services.uzhv_documents import render_personal_account_document, seed_uzhv_print_templates
    from delayu.services.uzhv_personal_account import ensure_personal_account

    seed_uzhv_print_templates(uzhv_subsystem)
    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Лицевая, 1")
    p = MunicipalPremise.objects.create(building=b, number="10", area_sqm="50", rooms=2)
    account = ensure_personal_account(p, user=uzhv_user)
    account.tenant_citizen = uzhv_citizen
    account.utility_services = "Отопление, ХВС"
    account.save()
    title, text = render_personal_account_document(account)
    assert account.account_number in text
    assert uzhv_citizen.full_name in text
    assert "Отопление" in text
    assert "ВЫПИСКА" in text or "выписка" in title.lower()


@pytest.mark.django_db
def test_private_managed_premise(uzhv_subsystem):
    from delayu.models_uzhv import PrivateManagedPremise

    PrivateManagedPremise.objects.create(
        subsystem=uzhv_subsystem,
        address="ул. Частная, 5",
        owner_name="Иванов И.И.",
    )
    assert PrivateManagedPremise.objects.filter(subsystem=uzhv_subsystem).count() == 1


@pytest.mark.django_db
def test_inspection_plan_links(uzhv_subsystem, uzhv_user):
    from delayu.models_uzhv import HousingInspection, HousingInspectionPlan, MunicipalBuilding
    from delayu.services.uzhv import next_inspection_plan_number

    plan = HousingInspectionPlan.objects.create(
        subsystem=uzhv_subsystem,
        plan_number=next_inspection_plan_number(uzhv_subsystem),
        title="Тестовый план",
        period_from=date(2026, 1, 1),
        period_to=date(2026, 6, 30),
        created_by=uzhv_user,
    )
    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Плановая, 1")
    HousingInspection.objects.create(
        subsystem=uzhv_subsystem,
        plan=plan,
        inspection_number="ПР-T-1",
        inspection_type=HousingInspection.InspectionType.UNPLANNED,
        building=b,
        planned_date=date(2026, 2, 1),
    )
    assert plan.inspections.count() == 1


@pytest.mark.django_db
def test_enforcement_proceeding(uzhv_subsystem):
    from delayu.models_uzhv import HousingCourtCase, HousingEnforcementProceeding

    court = HousingCourtCase.objects.create(
        subsystem=uzhv_subsystem,
        court_name="Суд",
        case_number="X-1",
        defendant_name="ООО Тест",
    )
    HousingEnforcementProceeding.objects.create(
        subsystem=uzhv_subsystem,
        court_case=court,
        proceeding_number="ИП-1",
        debtor_name="ООО Тест",
    )
    assert court.enforcement_proceedings.count() == 1


@pytest.mark.django_db
def test_reconstruction_zone_building(uzhv_subsystem):
    from delayu.models_uzhv import MunicipalBuilding

    MunicipalBuilding.objects.create(
        subsystem=uzhv_subsystem,
        address="ул. Реконструкция, 1",
        in_reconstruction_zone=True,
        reconstruction_program="Программа 2026",
    )
    assert MunicipalBuilding.objects.filter(subsystem=uzhv_subsystem, in_reconstruction_zone=True).count() == 1


@pytest.mark.django_db
def test_spawn_inspection_from_order(uzhv_subsystem):
    from delayu.models_uzhv import HousingInspection, HousingInspectionOrder, MunicipalBuilding
    from delayu.services.uzhv_inspection_orders import spawn_inspection_from_order

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Предписание, 1")
    order = HousingInspectionOrder.objects.create(
        subsystem=uzhv_subsystem,
        order_number="ПВ-T-1",
        addressee="УК Тест",
        building=b,
        check_subject="Содержание МКД",
        conduct_by=date(2026, 4, 1),
    )
    inspection = spawn_inspection_from_order(order)
    order.refresh_from_db()
    assert inspection.pk
    assert order.inspection_id == inspection.pk
    assert order.status == HousingInspectionOrder.Status.SCHEDULED
    assert inspection.check_subject == "Содержание МКД"


@pytest.mark.django_db
def test_otch4_extended_columns(uzhv_subsystem):
    from delayu.models_uzhv import HousingInspection, MunicipalBuilding
    from delayu.services.uzhv_reports import report_otch4_inspections

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Отчёт, 4")
    HousingInspection.objects.create(
        subsystem=uzhv_subsystem,
        inspection_number="ПР-О4-1",
        building=b,
        planned_date=date(2026, 3, 15),
        status=HousingInspection.Status.COMPLETED,
    )
    csv = report_otch4_inspections(uzhv_subsystem, date(2026, 3, 1), date(2026, 3, 31))
    assert "Протоколы АП" in csv
    assert "ПР-О4-1" in csv


@pytest.mark.django_db
def test_complete_inspection_order_on_inspection_complete(uzhv_subsystem):
    from delayu.models_uzhv import HousingInspection, HousingInspectionOrder, MunicipalBuilding
    from delayu.services.uzhv_inspection_orders import (
        complete_inspection_order_for_inspection,
        spawn_inspection_from_order,
    )

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Закрытие, 1")
    order = HousingInspectionOrder.objects.create(
        subsystem=uzhv_subsystem,
        order_number="ПВ-C-1",
        addressee="УК Закрытие",
        building=b,
        check_subject="Проверка",
        conduct_by=date(2026, 5, 1),
    )
    inspection = spawn_inspection_from_order(order)
    inspection.status = HousingInspection.Status.COMPLETED
    inspection.save(update_fields=["status"])
    assert complete_inspection_order_for_inspection(inspection) is True
    order.refresh_from_db()
    assert order.status == HousingInspectionOrder.Status.COMPLETED


@pytest.mark.django_db
def test_uzhv_search_inspection_order(uzhv_subsystem):
    from delayu.models_uzhv import HousingInspectionOrder, MunicipalBuilding

    b = MunicipalBuilding.objects.create(subsystem=uzhv_subsystem, address="ул. Поиск ПВ, 2")
    HousingInspectionOrder.objects.create(
        subsystem=uzhv_subsystem,
        order_number="ПВ-S-99",
        addressee="УК Поиск",
        building=b,
        check_subject="Тест",
        conduct_by=date(2026, 6, 1),
    )
    hits = uzhv_global_search(uzhv_subsystem, "пв:ПВ-S")
    assert hits
    assert hits[0]["type"] == "uzhv_inspection_order"


@pytest.mark.django_db
def test_register_appeal_outgoing(uzhv_subsystem, uzhv_appeal, uzhv_user):
    from delayu.models import Correspondence
    from delayu.services.uzhv_appeals import register_appeal_outgoing

    uzhv_appeal.status = HousingAppeal.Status.ANSWERED
    uzhv_appeal.answer_text = "Ответ по существу"
    uzhv_appeal.save()
    outgoing = register_appeal_outgoing(uzhv_appeal, user=uzhv_user)
    uzhv_appeal.refresh_from_db()
    assert outgoing.direction == Correspondence.Direction.OUT
    assert uzhv_appeal.outgoing_correspondence_id == outgoing.pk
    assert register_appeal_outgoing(uzhv_appeal, user=uzhv_user).pk == outgoing.pk


@pytest.mark.django_db
def test_appeal_status_history_on_register(uzhv_subsystem, uzhv_citizen, uzhv_user):
    from delayu.models_uzhv import HousingAppealStatusHistory
    from delayu.services.uzhv import register_housing_appeal

    appeal = register_housing_appeal(
        subsystem=uzhv_subsystem,
        user=uzhv_user,
        subject="Тест истории",
        citizen=uzhv_citizen,
    )
    assert HousingAppealStatusHistory.objects.filter(appeal=appeal).count() == 1
