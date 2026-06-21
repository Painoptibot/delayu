"""Развёртывание подсистемы АИС УЖВ (этап 1)."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from delayu.models import (
    LicenseEntitlement,
    ModuleCatalog,
    NotificationTemplate,
    NSIClassifier,
    NSIValue,
    Organization,
    ReportTemplate,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_uzhv import (
    HousingAdminProtocol,
    HousingAppeal,
    HousingCitizen,
    HousingContract,
    HousingCourtCase,
    HousingEnforcementProceeding,
    HousingInspection,
    HousingInspectionOrder,
    HousingInspectionPlan,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
    MunicipalBuilding,
    MunicipalPremise,
    OrphanHousingRecord,
    YoungFamilyRecord,
)
from delayu.services.scope import UZHV_MODULE_CODES
from delayu.services.uzhv_roles import ROLE_SPECS, perm_for_role
from delayu.services.uzhv import register_housing_appeal
from delayu.services.uzhv_low_income import calculate_low_income

User = get_user_model()


class Command(BaseCommand):
    help = "Создаёт подсистему АИС УЖВ, роли, пользователей и демо-данные"

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

        subsystem, _ = Subsystem.objects.update_or_create(
            code="uzhv",
            defaults={
                "name": 'АИС «УЖВ»',
                "description": (
                    "Автоматизированная информационная система управления "
                    "по жилищным вопросам (г. Краснодар)"
                ),
                "status": Subsystem.Status.ACTIVE,
                "primary_color": "#1e88e5",
                "industry_template": "uzhv",
            },
        )

        enabled = set(UZHV_MODULE_CODES)
        for mod in ModuleCatalog.objects.all():
            SubsystemModule.objects.update_or_create(
                subsystem=subsystem,
                module=mod,
                defaults={"enabled": mod.code in enabled},
            )
            if mod.code in enabled:
                LicenseEntitlement.objects.update_or_create(
                    subsystem=subsystem, module=mod, defaults={"valid_until": None}
                )

        org, _ = Organization.objects.update_or_create(
            subsystem=subsystem,
            code="uzhv",
            defaults={"name": "Управление по жилищным вопросам"},
        )

        roles_spec = [(code, meta["label"], meta.get("system", False)) for code, meta in ROLE_SPECS.items()]
        roles = {}
        for code, name, is_system in roles_spec:
            roles[code], _ = Role.objects.update_or_create(
                subsystem=subsystem,
                code=code,
                defaults={"name": name, "is_system": is_system},
            )

        for role in roles.values():
            for mod in ModuleCatalog.objects.all():
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults=perm_for_role(role.code, mod.code),
                )

        users_spec = [
            ("uzhv_admin", "uzhv_admin", "Администратор", "УЖВ", "uzhv_admin"),
            ("uzhv_spec", "uzhv_spec", "Елена", "Специалистова", "uzhv_queue_spec"),
            ("uzhv_mgr", "uzhv_mgr", "Пётр", "Руководителев", "uzhv_head"),
            ("uzhv_orphan", "uzhv_orphan", "Ольга", "Сироткина", "uzhv_orphan_spec"),
            ("uzhv_contract", "uzhv_contract", "Сергей", "Договоров", "uzhv_contract_spec"),
        ]
        for username, password, first, last, role_code in users_spec:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@uzhv.local",
                    "first_name": first,
                    "last_name": last,
                },
            )
            if created:
                user.set_password(password)
                user.save()
            SubsystemMembership.objects.update_or_create(
                user=user,
                subsystem=subsystem,
                defaults={
                    "organization": org,
                    "role": roles[role_code],
                    "is_default": True,
                },
            )

        # Сохранить platform admin в pilot, uzhv users default to uzhv
        SubsystemMembership.objects.filter(user__username="admin", subsystem=subsystem).delete()

        spec_user = User.objects.get(username="uzhv_spec")
        self._seed_nsi(subsystem)
        self._seed_reports(subsystem)
        self._seed_notification_templates(subsystem)
        self._seed_integrations(subsystem)
        self._seed_sso_demo(subsystem)
        self._seed_domain(subsystem, spec_user)

        self.stdout.write(self.style.SUCCESS("АИС УЖВ развёрнута (code=uzhv)"))
        self.stdout.write("  uzhv_admin / uzhv_admin — администратор подсистемы")
        self.stdout.write("  uzhv_spec / uzhv_spec — специалист")
        self.stdout.write("  uzhv_orphan / uzhv_orphan — специалист (дети-сироты)")
        self.stdout.write("  uzhv_contract / uzhv_contract — специалист по договорам")
        self.stdout.write("  admin / admin — платформа (superuser, глобальные настройки)")

    def _seed_notification_templates(self, subsystem):
        NotificationTemplate.objects.update_or_create(
            subsystem=subsystem,
            event_code="uzhv_deadline_urgent",
            channel=NotificationTemplate.Channel.EMAIL,
            defaults={
                "subject": "УЖВ: {title}",
                "body": "{body}\n\nОткрыть в системе: {link}",
                "is_active": True,
            },
        )
        NotificationTemplate.objects.update_or_create(
            subsystem=subsystem,
            event_code="uzhv_deadline_urgent",
            channel=NotificationTemplate.Channel.SMS,
            defaults={
                "subject": "УЖВ: {title}",
                "body": "{body}",
                "is_active": True,
            },
        )
        status_templates = (
            (
                "uzhv_appeal_status_changed",
                "УЖВ: обращение {appeal_number}",
                "Статус: {from_status} → {to_status}\n{subject}\n{link}",
            ),
            (
                "uzhv_case_status_changed",
                "УЖВ: дело {case_number}",
                "Статус: {from_status} → {to_status}\n{case}\n{link}",
            ),
        )
        for event_code, subject, body in status_templates:
            for channel in (
                NotificationTemplate.Channel.IN_APP,
                NotificationTemplate.Channel.SMS,
                NotificationTemplate.Channel.EMAIL,
            ):
                NotificationTemplate.objects.update_or_create(
                    subsystem=subsystem,
                    event_code=event_code,
                    channel=channel,
                    defaults={"subject": subject, "body": body, "is_active": True},
                )

    def _seed_integrations(self, subsystem):
        import os

        from delayu.models import IntegrationEndpoint, MailTransportConfig, MessengerChannel, UserProfile

        email_host = (os.environ.get("EMAIL_HOST") or "").strip()
        imap_host = (os.environ.get("UZHV_IMAP_HOST") or "").strip()
        MailTransportConfig.objects.update_or_create(
            subsystem=subsystem,
            defaults={
                "is_enabled": bool(email_host),
                "default_from_email": os.environ.get("DEFAULT_FROM_EMAIL", "noreply@uzhv.local"),
                "smtp_host": email_host,
                "smtp_port": int(os.environ.get("EMAIL_PORT", "587") or 587),
                "smtp_use_tls": os.environ.get("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes"),
                "smtp_username": (os.environ.get("EMAIL_HOST_USER") or "").strip(),
                "smtp_password": (os.environ.get("EMAIL_HOST_PASSWORD") or "").strip(),
                "imap_enabled": bool(imap_host),
                "imap_host": imap_host,
                "imap_port": int(os.environ.get("UZHV_IMAP_PORT", "993") or 993),
                "imap_use_ssl": os.environ.get("UZHV_IMAP_SSL", "true").lower() in ("1", "true", "yes"),
                "imap_username": (os.environ.get("UZHV_IMAP_USER") or "").strip(),
                "imap_password": (os.environ.get("UZHV_IMAP_PASSWORD") or "").strip(),
                "imap_folder": (os.environ.get("UZHV_IMAP_FOLDER") or "INBOX").strip(),
            },
        )

        webhook_url = (os.environ.get("DELAYU_WEBHOOK_URL") or "").strip()
        n8n_url = (os.environ.get("DELAYU_N8N_WEBHOOK_URL") or "").strip()

        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="mfc_uzhv",
            defaults={
                "name": "МФЦ (входящие заявления)",
                "endpoint_type": IntegrationEndpoint.EndpointType.GATEWAY,
                "description": "POST JSON — заявление, принятое в МФЦ (I-07)",
                "is_active": True,
                "config": {
                    "allow_inbound": True,
                    "inbound_handler": "uzhv.mfc.application",
                    "inbound_secret": "uzhv-mfc-demo-secret",
                },
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="epgu_uzhv",
            defaults={
                "name": "ЕПГУ / портал обращений (входящий)",
                "endpoint_type": IntegrationEndpoint.EndpointType.GATEWAY,
                "description": "POST JSON — регистрация обращения из внешнего портала",
                "is_active": True,
                "config": {
                    "allow_inbound": True,
                    "inbound_handler": "uzhv.epgu.appeal",
                    "inbound_secret": "uzhv-epgu-demo-secret",
                },
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="telegram_inbound",
            defaults={
                "name": "Telegram inbound (журнал)",
                "endpoint_type": IntegrationEndpoint.EndpointType.GATEWAY,
                "is_active": True,
                "config": {"allow_inbound": True, "inbound_handler": "telegram.update"},
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="n8n_uzhv",
            defaults={
                "name": "n8n / Zapier (исходящие события)",
                "endpoint_type": IntegrationEndpoint.EndpointType.WEBHOOK,
                "is_active": bool(n8n_url),
                "config": {
                    "webhook_url": n8n_url or "https://your-n8n.example/webhook/uzhv",
                    "events": ["*"],
                },
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="external_1c_uzhv",
            defaults={
                "name": "1С: учётные дела (входящий JSON)",
                "endpoint_type": IntegrationEndpoint.EndpointType.EXTERNAL_1C,
                "is_active": True,
                "config": {
                    "allow_inbound": True,
                    "inbound_handler": "external.1c.case",
                    "inbound_secret": "uzhv-1c-demo-secret",
                },
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="webhook_uzhv",
            defaults={
                "name": "Webhook событий УЖВ",
                "endpoint_type": IntegrationEndpoint.EndpointType.WEBHOOK,
                "description": "Исходящие POST при смене статусов обращений и дел",
                "is_active": bool(webhook_url),
                "config": {
                    "webhook_url": webhook_url or "https://example.com/hooks/uzhv",
                    "secret": (os.environ.get("DELAYU_WEBHOOK_SECRET") or "").strip(),
                    "events": [
                        "uzhv.appeal.status_changed",
                        "uzhv.case.status_changed",
                    ],
                },
            },
        )
        MessengerChannel.objects.update_or_create(
            subsystem=subsystem,
            code="max_uzhv",
            defaults={
                "name": "MAX (уведомления)",
                "channel_type": MessengerChannel.ChannelType.MAX,
                "webhook_url": "demo:max",
                "is_active": True,
                "notes": "Укажите URL API MAX; иначе — запись в журнал доставки",
            },
        )
        MessengerChannel.objects.update_or_create(
            subsystem=subsystem,
            code="telegram_uzhv",
            defaults={
                "name": "Telegram Bot УЖВ",
                "channel_type": MessengerChannel.ChannelType.TELEGRAM,
                "webhook_url": "https://api.telegram.org/bot/demo/webhook",
                "is_active": True,
                "notes": "Укажите реальный токен: https://api.telegram.org/bot<TOKEN>/",
            },
        )
        for username, tg in (
            ("uzhv_spec", "uzhv_spec"),
            ("uzhv_admin", "uzhv_admin"),
        ):
            user = User.objects.filter(username=username).first()
            if not user:
                continue
            UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    "phone_mobile": "+79001234567",
                    "telegram": f"@{tg}",
                    "telegram_chat_id": "100000001",
                },
            )

    def _seed_sso_demo(self, subsystem):
        from delayu.models import SsoProvider

        SsoProvider.objects.update_or_create(
            subsystem=subsystem,
            name="ЕСИА (демо)",
            defaults={
                "provider_type": SsoProvider.ProviderType.ESIA,
                "client_id": "demo",
                "is_active": True,
                "metadata": {"demo": True},
            },
        )
        SsoProvider.objects.update_or_create(
            subsystem=subsystem,
            name="Active Directory (OIDC)",
            defaults={
                "provider_type": SsoProvider.ProviderType.OIDC,
                "client_id": "",
                "is_active": False,
                "metadata": {
                    "authorization_endpoint": "https://login.microsoftonline.com/TENANT/oauth2/v2.0/authorize",
                    "token_endpoint": "https://login.microsoftonline.com/TENANT/oauth2/v2.0/token",
                    "scope": "openid profile email",
                    "hint": "Замените TENANT; для AD FS укажите endpoints вашего IdP",
                },
            },
        )

    def _seed_nsi(self, subsystem):
        pm, _ = NSIClassifier.objects.update_or_create(
            subsystem=subsystem,
            code="uzhv_subsistence_minimum",
            defaults={"name": "Прожиточный минимум (УЖВ), ₽", "description": "На душу населения"},
        )
        NSIValue.objects.update_or_create(
            classifier=pm, code="16089", defaults={"name": "Краснодарский край (ориентир)", "sort_order": 1}
        )
        pl, _ = NSIClassifier.objects.update_or_create(
            subsystem=subsystem,
            code="uzhv_property_limit",
            defaults={"name": "Предел стоимости имущества на 1 чел., ₽", "description": "Малоимущие"},
        )
        NSIValue.objects.update_or_create(
            classifier=pl, code="250000", defaults={"name": "Предельная стоимость", "sort_order": 1}
        )
        from delayu.services.uzhv_nsi import seed_uzhv_nsi_classifiers

        seed_uzhv_nsi_classifiers(subsystem)

    def _seed_reports(self, subsystem):
        specs = [
            ("otch-1", "ОТЧ-1 — Список на учёте", "uzhv_otch1"),
            ("otch-2", "ОТЧ-2 — Предоставление жилья", "uzhv_otch2"),
            ("otch-3", "ОТЧ-3 — Договоры соцнайма", "uzhv_otch3"),
            ("otch-4", "ОТЧ-4 — Результаты проверок", "uzhv_otch4"),
            ("otch-5", "ОТЧ-5 — Обращения", "uzhv_otch5"),
            ("otch-6", "ОТЧ-6 — Движение жилфонда", "uzhv_otch6"),
            ("otch-7", "ОТЧ-7 — Дети-сироты", "uzhv_otch7"),
            ("otch-8", "ОТЧ-8 — Межведомственные запросы", "uzhv_otch8"),
            ("otch-9", "ОТЧ-9 — Расселение аварийного фонда", "uzhv_otch9"),
            ("unfit-premises", "Непригодные помещения", "uzhv_unfit"),
            ("otch-10", "ОТЧ-10 — Исполнение предписаний", "uzhv_otch10"),
        ]
        for code, name, qk in specs:
            ReportTemplate.objects.update_or_create(
                subsystem=subsystem,
                code=code,
                defaults={
                    "name": name,
                    "query_key": qk,
                    "columns": [],
                    "report_kind": ReportTemplate.ReportKind.REGULATORY,
                    "is_active": True,
                },
            )

    def _seed_domain(self, subsystem, assignee):
        HousingAppeal.objects.filter(subsystem=subsystem).delete()
        HousingInteragencyRequest.objects.filter(subsystem=subsystem).delete()
        HousingAdminProtocol.objects.filter(inspection__subsystem=subsystem).delete()
        HousingCourtCase.objects.filter(subsystem=subsystem).delete()
        HousingEnforcementProceeding.objects.filter(subsystem=subsystem).delete()
        HousingInspectionPlan.objects.filter(subsystem=subsystem).delete()
        HousingInspectionOrder.objects.filter(subsystem=subsystem).delete()
        HousingPrescription.objects.filter(inspection__subsystem=subsystem).delete()
        HousingInspection.objects.filter(subsystem=subsystem).delete()
        YoungFamilyRecord.objects.filter(case__subsystem=subsystem).delete()
        OrphanHousingRecord.objects.filter(case__subsystem=subsystem).delete()
        HousingContract.objects.filter(subsystem=subsystem).delete()
        HousingQueueCase.objects.filter(subsystem=subsystem).delete()
        HousingCitizen.objects.filter(subsystem=subsystem).delete()
        MunicipalBuilding.objects.filter(subsystem=subsystem).delete()

        citizens = []
        samples = [
            ("Иванов", "Иван", "Иванович", "123-456-789 01", date(1985, 3, 12)),
            ("Петрова", "Мария", "Сергеевна", "234-567-890 12", date(1990, 7, 22)),
            ("Сидоров", "Алексей", "Петрович", "345-678-901 23", date(1978, 11, 5)),
            ("Козлова", "Анна", "Дмитриевна", "456-789-012 34", date(2002, 1, 15)),
        ]
        for ln, fn, mn, snils, bd in samples:
            citizens.append(
                HousingCitizen.objects.create(
                    subsystem=subsystem,
                    last_name=ln,
                    first_name=fn,
                    middle_name=mn,
                    snils=snils,
                    birth_date=bd,
                    reg_address="г. Краснодар, ул. Красная, д. 1",
                )
            )

        cases_data = [
            ("УЖВ-2026-001", citizens[0], HousingQueueCase.Category.LOW_INCOME, 1),
            ("УЖВ-2026-002", citizens[1], HousingQueueCase.Category.YOUNG_FAMILY, 2),
            ("УЖВ-2026-003", citizens[2], HousingQueueCase.Category.GENERAL, 3),
            ("УЖВ-2026-004", citizens[3], HousingQueueCase.Category.ORPHAN, 4),
        ]
        case_objs = []
        for num, citizen, cat, pos in cases_data:
            case = HousingQueueCase.objects.create(
                subsystem=subsystem,
                citizen=citizen,
                case_number=num,
                category=cat,
                status=HousingQueueCase.Status.QUEUED,
                registered_at=timezone.now().date(),
                queue_position=pos,
                assignee=assignee,
                income_verified=cat == HousingQueueCase.Category.LOW_INCOME,
            )
            if cat == HousingQueueCase.Category.LOW_INCOME:
                case.household_size = 3
                case.monthly_income = "35000"
                case.property_value = "400000"
                res = calculate_low_income(
                    subsystem=subsystem,
                    monthly_income=case.monthly_income,
                    household_size=case.household_size,
                    property_value=case.property_value,
                )
                case.per_capita_income = res["per_capita_income"]
                case.low_income_eligible = res["eligible"]
                case.low_income_conclusion = res["conclusion"]
                case.low_income_calculated_at = timezone.now()
                case.save()
            case_objs.append(case)

        from delayu.services.uzhv_low_income import compute_low_income_review_due

        pending = case_objs[2]
        app_date = timezone.now().date() - timedelta(days=25)
        pending.low_income_application_at = app_date
        pending.low_income_review_due_at = compute_low_income_review_due(app_date, subsystem)
        pending.save(
            update_fields=["low_income_application_at", "low_income_review_due_at", "updated_at"]
        )

        yf_case = case_objs[1]
        YoungFamilyRecord.objects.create(
            case=yf_case,
            spouse_last_name="Петров",
            spouse_first_name="Игорь",
            spouse_middle_name="Андреевич",
            marriage_date=date(2018, 6, 1),
            children_count=2,
            program=YoungFamilyRecord.Program.JSK,
            meets_criteria=True,
        )
        orphan_case = case_objs[3]
        OrphanHousingRecord.objects.create(
            case=orphan_case,
            mintrud_decision_number="МТ-2026-0142",
            mintrud_decision_date=date(2026, 2, 10),
            housing_status=OrphanHousingRecord.HousingStatus.IN_LIST,
            notes="Включена в список на обеспечение жильём",
        )

        from delayu.services.uzhv_map import geocode_address

        addr1 = "г. Краснодар, ул. Северная, д. 10"
        lat1, lng1 = geocode_address(addr1)
        b1 = MunicipalBuilding.objects.create(
            subsystem=subsystem,
            address=addr1,
            floors=9,
            year_built=1985,
            latitude=lat1,
            longitude=lng1,
        )
        addr2 = "г. Краснодар, ул. Ставропольская, д. 45"
        lat2, lng2 = geocode_address(addr2)
        b2 = MunicipalBuilding.objects.create(
            subsystem=subsystem,
            address=addr2,
            floors=5,
            year_built=1972,
            condition=MunicipalBuilding.Condition.RENOVATION,
            total_area_sqm="2840.50",
            residents_count=42,
            in_resettlement_program=True,
            latitude=lat2,
            longitude=lng2,
            notes="Включён в программу расселения аварийного жилфонда",
        )
        p1 = MunicipalPremise.objects.create(
            building=b1, number="12", area_sqm="54.2", rooms=2, status=MunicipalPremise.Status.FREE
        )
        MunicipalPremise.objects.create(
            building=b1, number="34", area_sqm="61.0", rooms=3, status=MunicipalPremise.Status.OCCUPIED
        )
        MunicipalPremise.objects.create(
            building=b2, number="7", area_sqm="48.5", rooms=2, status=MunicipalPremise.Status.FREE
        )
        MunicipalPremise.objects.create(
            building=b2,
            number="1",
            area_sqm="42.0",
            rooms=2,
            status=MunicipalPremise.Status.FREE,
            unfit_for_living=True,
            unfit_decision_ref="АКТ-2025-044",
            unfit_decision_at=date(2025, 8, 15),
            unfit_reason="Помещение признано непригодным для проживания",
            usable_for_purpose=False,
        )
        MunicipalPremise.objects.create(
            building=b1,
            number="5",
            area_sqm="38.0",
            rooms=1,
            status=MunicipalPremise.Status.FREE,
            specialized_orphan=True,
        )

        HousingContract.objects.create(
            subsystem=subsystem,
            contract_number="ДН-2024-089",
            contract_type=HousingContract.ContractType.SOCIAL,
            citizen=citizens[2],
            premise=p1,
            signed_at=date(2024, 6, 1),
            is_active=True,
        )
        from delayu.models_uzhv import HousingContractConsent

        admin_user = User.objects.get(username="uzhv_admin")
        demo_contract = HousingContract.objects.get(subsystem=subsystem, contract_number="ДН-2024-089")
        HousingContractConsent.objects.create(
            contract=demo_contract,
            consent_type=HousingContractConsent.ConsentType.MOVE_IN,
            decision=HousingContractConsent.Decision.APPROVED,
            subject="Супруг(а) Петрова М.И.",
            document_number="СВ-2024-12",
            registered_at=date(2024, 7, 10),
            created_by=admin_user,
        )

        from delayu.models_uzhv import (
            HousingPersonalAccountMember,
            PrivateManagedPremise,
        )
        from delayu.services.uzhv_personal_account import ensure_personal_account

        ls = ensure_personal_account(p1, user=admin_user)
        ls.tenant_citizen = citizens[2]
        ls.utility_services = (
            "Отопление, холодное и горячее водоснабжение, водоотведение, электроснабжение"
        )
        ls.save()
        HousingPersonalAccountMember.objects.create(
            account=ls,
            full_name=citizens[2].full_name,
            relation=HousingPersonalAccountMember.Relation.HEAD,
        )
        HousingPersonalAccountMember.objects.create(
            account=ls,
            full_name="Петрова Мария Ивановна",
            relation=HousingPersonalAccountMember.Relation.SPOUSE,
        )
        PrivateManagedPremise.objects.create(
            subsystem=subsystem,
            address="г. Краснодар, ул. Частная, д. 3",
            premise_number="2",
            area_sqm="56.0",
            rooms=2,
            owner_name="Сидоров Пётр Александрович",
            management_since=date(2023, 1, 15),
        )

        insp = HousingInspection.objects.create(
            subsystem=subsystem,
            inspection_number="ПР-2026-001",
            inspection_type=HousingInspection.InspectionType.PLANNED,
            object_type=HousingInspection.ObjectType.MKD,
            building=b2,
            check_subject="Содержание общего имущества МКД",
            planned_date=timezone.now().date() - timedelta(days=14),
            completed_date=timezone.now().date() - timedelta(days=10),
            inspector=assignee,
            status=HousingInspection.Status.COMPLETED,
            result_summary="Выявлены нарушения по содержанию подъездов и кровли.",
            violations_found=True,
        )
        pres_active = HousingPrescription.objects.create(
            inspection=insp,
            prescription_number="ПРЕД-2026-001",
            issued_at=timezone.now().date() - timedelta(days=9),
            due_date=timezone.now().date() + timedelta(days=21),
            description="Устранить протечки кровли, привести в порядок подъезд №1.",
            status=HousingPrescription.Status.IN_PROGRESS,
        )
        pres_overdue = HousingPrescription.objects.create(
            inspection=insp,
            prescription_number="ПРЕД-2025-088",
            issued_at=date(2025, 11, 1),
            due_date=date(2025, 12, 15),
            description="Привести в соответствие систему вентиляции (просрочено — демо).",
            status=HousingPrescription.Status.OVERDUE,
        )
        HousingCourtCase.objects.create(
            subsystem=subsystem,
            inspection=insp,
            prescription=pres_overdue,
            court_name="Краснодарский краевой суд",
            case_number="А32-12345/2026",
            check_address=b2.address,
            defendant_name="ООО «УК Ставропольская»",
            next_hearing_date=timezone.now().date() + timedelta(days=14),
            status=HousingCourtCase.Status.ENFORCEMENT,
            ufssp_reference="12345/26/23001-ИП",
            notes="Иск об обязании устранить нарушения жилищного законодательства",
        )
        demo_court = HousingCourtCase.objects.get(subsystem=subsystem, case_number="А32-12345/2026")
        HousingEnforcementProceeding.objects.create(
            subsystem=subsystem,
            court_case=demo_court,
            proceeding_number="12345/26/23001-ИП",
            debtor_name=demo_court.defendant_name,
            check_address=demo_court.check_address,
            court_decision="Обязать устранить нарушения в срок 30 дней",
            initiated_at=date(2026, 3, 1),
            bailiff_office="ОСП по г. Краснодару",
            status=HousingEnforcementProceeding.Status.IN_PROGRESS,
        )
        demo_plan = HousingInspectionPlan.objects.create(
            subsystem=subsystem,
            plan_number=f"ПЛ-{timezone.now().year}-001",
            title="Внеплановые проверки содержания МКД",
            period_from=timezone.now().date(),
            period_to=timezone.now().date() + timedelta(days=90),
            basis="Обращения граждан и предписания прокуратуры",
            status=HousingInspectionPlan.Status.APPROVED,
            approved_at=timezone.now().date(),
            created_by=admin_user,
        )
        HousingInspectionOrder.objects.create(
            subsystem=subsystem,
            order_number=f"ПВ-{timezone.now().year}-001",
            addressee="ООО «УК Северная»",
            object_type=HousingInspection.ObjectType.UK,
            building=b1,
            check_subject="Содержание общего имущества МКД",
            plan=demo_plan,
            issued_at=timezone.now().date() - timedelta(days=5),
            conduct_by=timezone.now().date() + timedelta(days=10),
            status=HousingInspectionOrder.Status.ISSUED,
        )
        HousingInspection.objects.create(
            subsystem=subsystem,
            plan=demo_plan,
            inspection_number="ПР-2026-002",
            inspection_type=HousingInspection.InspectionType.UNPLANNED,
            object_type=HousingInspection.ObjectType.MKD,
            building=b1,
            check_subject="Содержание общего имущества МКД",
            planned_date=timezone.now().date() + timedelta(days=7),
            inspector=assignee,
            status=HousingInspection.Status.PLANNED,
        )
        b1.in_reconstruction_zone = True
        b1.reconstruction_program = "Комплексная реконструкция квартала"
        b1.reconstruction_since = date(2025, 6, 1)
        b1.save(update_fields=["in_reconstruction_zone", "reconstruction_program", "reconstruction_since"])
        HousingAdminProtocol.objects.create(
            inspection=insp,
            protocol_number="ПА-2026-003",
            protocol_date=timezone.now().date() - timedelta(days=8),
            legal_article="ст. 14.1 Закона КК № 608-КЗ",
            violator_name="ООО «УК Ставропольская»",
            fine_amount="5000.00",
            status=HousingAdminProtocol.Status.ISSUED,
            notes="Нарушение правил содержания общего имущества МКД",
        )
        HousingInteragencyRequest.objects.create(
            subsystem=subsystem,
            request_number="МВ-2026-001",
            request_type=HousingInteragencyRequest.RequestType.ROSREESTR,
            channel=HousingInteragencyRequest.Channel.MANUAL,
            recipient_name="Управление Росреестра по КК",
            subject="Выписка ЕГРН на жилое помещение (дело дети-сироты)",
            housing_case=orphan_case,
            citizen=citizens[3],
            sent_at=timezone.now().date() - timedelta(days=12),
            due_date=timezone.now().date() + timedelta(days=18),
            status=HousingInteragencyRequest.Status.AWAITING,
            created_by=admin_user,
        )
        HousingInteragencyRequest.objects.create(
            subsystem=subsystem,
            request_number="МВ-2025-042",
            request_type=HousingInteragencyRequest.RequestType.MINTRUD,
            channel=HousingInteragencyRequest.Channel.FILE,
            recipient_name="Минтруд и социального развития КК",
            subject="Подтверждение включения в список детей-сирот",
            housing_case=orphan_case,
            citizen=citizens[3],
            sent_at=date(2025, 10, 5),
            due_date=date(2025, 11, 5),
            answered_at=date(2025, 10, 28),
            response_summary="Положительное решение № МТ-2026-0142 направлено в адрес УЖВ",
            status=HousingInteragencyRequest.Status.ANSWERED,
            created_by=admin_user,
        )
        register_housing_appeal(
            subsystem=subsystem,
            user=admin_user,
            subject="Запрос о положении на учёте нуждающихся",
            body="Прошу сообщить очерёдность и срок предоставления жилого помещения.",
            citizen=citizens[0],
            assignee=assignee,
            received_at=timezone.now().date() - timedelta(days=25),
        )
        register_housing_appeal(
            subsystem=subsystem,
            user=admin_user,
            subject="Жалоба на срок рассмотрения заявления",
            body="Заявление подано более месяца назад, ответ не получен.",
            citizen=citizens[1],
            assignee=assignee,
            received_at=timezone.now().date() - timedelta(days=32),
        )

        from delayu.services.uzhv_documents import seed_uzhv_print_templates

        seed_uzhv_print_templates(subsystem)
