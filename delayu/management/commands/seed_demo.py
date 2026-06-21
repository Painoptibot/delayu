from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from django.core.files.base import ContentFile

from delayu.models import (
    ActivityEvent,
    BPMTemplate,
    CaseFile,
    CaseRegulation,
    DocumentFile,
    ChatRoom,
    Comment,
    MessengerChannel,
    ObjectSubscription,
    VideoMeeting,
    Correspondence,
    CorrespondenceEvent,
    PrintTemplate,
    Department,
    Favorite,
    IntegrationEndpoint,
    KnowledgeArticle,
    LicenseEntitlement,
    ModuleCatalog,
    Notification,
    NSIClassifier,
    NSIValue,
    Organization,
    RegistryRecord,
    RegistryType,
    RegulatoryReportSubmission,
    ReportTemplate,
    Role,
    RoleModulePermission,
    SavedFilter,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
    SLARule,
    TaskItem,
)
from delayu.models_business import Position, UserAssignment, UserProfile
from delayu.services import bpm
from delayu.services.users import get_or_create_profile

User = get_user_model()


class Command(BaseCommand):
    help = "Полные демо-данные платформы"

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

        subsystem, _ = Subsystem.objects.update_or_create(
            code="pilot",
            defaults={
                "name": "Пилотная подсистема",
                "description": "Демо-контур платформы ДелаЮ",
                "status": Subsystem.Status.ACTIVE,
                "primary_color": "#666cff",
            },
        )

        for mod in ModuleCatalog.objects.all():
            SubsystemModule.objects.update_or_create(
                subsystem=subsystem, module=mod, defaults={"enabled": True}
            )
            LicenseEntitlement.objects.update_or_create(
                subsystem=subsystem, module=mod, defaults={"valid_until": None}
            )

        org, _ = Organization.objects.update_or_create(
            subsystem=subsystem, code="head", defaults={"name": "Головная организация"}
        )
        dept, _ = Department.objects.update_or_create(
            organization=org, code="opr", defaults={"name": "Операционный отдел"}
        )

        admin_role, _ = Role.objects.update_or_create(
            subsystem=subsystem, code="admin", defaults={"name": "Администратор", "is_system": True}
        )
        spec_role, _ = Role.objects.update_or_create(
            subsystem=subsystem, code="specialist", defaults={"name": "Специалист", "is_system": True}
        )
        mgr_role, _ = Role.objects.update_or_create(
            subsystem=subsystem, code="manager", defaults={"name": "Руководитель", "is_system": True}
        )

        for role in (admin_role, spec_role, mgr_role):
            for mod in ModuleCatalog.objects.all():
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults={
                        "can_view": True,
                        "can_create": role.code != "manager",
                        "can_change": True,
                        "can_delete": role.code == "admin",
                    },
                )

        admin_user, created = User.objects.get_or_create(
            username="admin",
            defaults={
                "email": "admin@delayu.local",
                "is_staff": True,
                "is_superuser": True,
                "first_name": "Администратор",
                "last_name": "Платформы",
            },
        )
        if created:
            admin_user.set_password("admin")
            admin_user.save()

        demo_user, created = User.objects.get_or_create(
            username="demo",
            defaults={"email": "demo@delayu.local", "first_name": "Иван", "last_name": "Специалист"},
        )
        if created:
            demo_user.set_password("demo")
            demo_user.save()

        mgr_user, created = User.objects.get_or_create(
            username="manager",
            defaults={"email": "mgr@delayu.local", "first_name": "Мария", "last_name": "Руководитель"},
        )
        if created:
            mgr_user.set_password("manager")
            mgr_user.save()

        dept_it, _ = Department.objects.update_or_create(
            organization=org,
            code="it",
            defaults={
                "name": "Отдел информационных технологий",
                "parent": dept,
                "manager": admin_user,
            },
        )
        Position.objects.update_or_create(
            department=dept,
            code="head",
            defaults={"name": "Начальник отдела", "headcount": 1},
        )
        pos_spec, _ = Position.objects.update_or_create(
            department=dept_it,
            code="spec",
            defaults={"name": "Специалист", "headcount": 3},
        )

        memberships = [
            (admin_user, admin_role),
            (demo_user, spec_role),
            (mgr_user, mgr_role),
        ]
        demo_profiles = {
            "admin": {
                "middle_name": "Системович",
                "phone": "+7 (495) 100-00-01",
                "position_title": "Администратор платформы",
                "employee_number": "ADM-001",
                "department_text": "ИТ",
            },
            "demo": {
                "middle_name": "Петрович",
                "phone": "+7 (916) 200-00-02",
                "position_title": "Специалист",
                "tab_number": "00042",
                "hire_date": timezone.now().date().replace(year=timezone.now().year - 2),
            },
            "manager": {
                "middle_name": "Сергеевна",
                "phone": "+7 (495) 300-00-03",
                "position_title": "Руководитель отдела",
                "manager_name": "Директор",
            },
        }
        for user, role in memberships:
            SubsystemMembership.objects.update_or_create(
                user=user,
                subsystem=subsystem,
                organization=org,
                role=role,
                defaults={"is_default": True},
            )
            profile = get_or_create_profile(user)
            profile.active_subsystem = subsystem
            for key, val in demo_profiles.get(user.username, {}).items():
                setattr(profile, key, val)
            profile.save()

        UserAssignment.objects.get_or_create(
            user=demo_user, department=dept_it, position=pos_spec
        )

        rt, _ = RegistryType.objects.update_or_create(
            subsystem=subsystem,
            code="counterparties",
            defaults={
                "name": "Контрагенты",
                "field_schema": [{"key": "name", "label": "Наименование"}, {"key": "inn", "label": "ИНН"}],
            },
        )
        RegistryRecord.objects.get_or_create(
            registry_type=rt,
            organization=org,
            external_id="1",
            defaults={"data": {"name": "ООО Пример", "inn": "7700000000"}, "created_by": admin_user},
        )
        rt_emp, _ = RegistryType.objects.update_or_create(
            subsystem=subsystem,
            code="employees",
            defaults={
                "name": "Сотрудники (демо)",
                "description": "Упрощённый кадровый справочник",
                "field_schema": [
                    {"key": "fio", "label": "ФИО", "required": True},
                    {"key": "position", "label": "Должность", "required": False},
                ],
                "sort_order": 2,
            },
        )
        RegistryRecord.objects.get_or_create(
            registry_type=rt_emp,
            organization=org,
            external_id="demo-1",
            defaults={
                "data": {"fio": "Иванов Иван Иванович", "position": "Специалист"},
                "created_by": admin_user,
            },
        )

        cases_data = [
            ("PILOT-2026-0001", "Обращение гражданина по срокам", CaseFile.Status.IN_PROGRESS, demo_user),
            ("PILOT-2026-0002", "Согласование служебной записки", CaseFile.Status.WAITING, demo_user),
            ("PILOT-2026-0003", "Подготовка ответа на входящее", CaseFile.Status.NEW, mgr_user),
        ]
        case_objs = []
        for num, title, st, assignee in cases_data:
            c, _ = CaseFile.objects.update_or_create(
                subsystem=subsystem,
                number=num,
                defaults={
                    "organization": org,
                    "title": title,
                    "status": st,
                    "assignee": assignee,
                    "created_by": admin_user,
                    "due_date": timezone.now().date() + timedelta(days=3),
                    "description": "Демо-дело для испытаний платформы.",
                },
            )
            case_objs.append(c)

        today = timezone.now().date()
        for i, c in enumerate(case_objs):
            TaskItem.objects.update_or_create(
                subsystem=subsystem,
                case=c,
                title=f"Задача по делу {c.number}",
                defaults={
                    "assignee": c.assignee,
                    "due_date": today + timedelta(days=i + 1),
                    "start_date": today,
                    "duration_days": 3 + i,
                    "kanban_column": TaskItem.KanbanColumn.TODO if i == 0 else TaskItem.KanbanColumn.IN_PROGRESS,
                },
            )

        doc1, _ = DocumentFile.objects.get_or_create(
            subsystem=subsystem,
            case=case_objs[0],
            title="Скан заявления гражданина",
            version=1,
            is_current=True,
            defaults={
                "doc_type": DocumentFile.DocType.SCAN,
                "description": "Демо-вложение к делу PILOT-2026-0001",
                "uploaded_by": demo_user,
                "file": ContentFile(b"Demo document content", name="zayavlenie.txt"),
            },
        )
        if not doc1.file:
            doc1.file.save("zayavlenie.txt", ContentFile(b"Demo document content"), save=True)

        from delayu.services.correspondence import log_event

        in_corr, created_in = Correspondence.objects.get_or_create(
            subsystem=subsystem,
            reg_number="ВХ-2026-0001",
            defaults={
                "direction": Correspondence.Direction.IN,
                "reg_date": timezone.now().date(),
                "subject": "Заявление о предоставлении информации",
                "counterparty": "Гражданин Иванов И.И.",
                "status": Correspondence.Status.IN_WORK,
                "assignee": demo_user,
                "created_by": admin_user,
                "case": case_objs[0],
            },
        )
        if created_in:
            from delayu.models import RegistrationJournalEntry

            RegistrationJournalEntry.objects.get_or_create(
                correspondence=in_corr, defaults={"operator": admin_user}
            )
            log_event(
                in_corr,
                CorrespondenceEvent.EventType.REGISTERED,
                f"Зарегистрировано {in_corr.reg_number}",
                actor=admin_user,
            )

        Correspondence.objects.get_or_create(
            subsystem=subsystem,
            reg_number="ИСХ-2026-0001",
            defaults={
                "direction": Correspondence.Direction.OUT,
                "reg_date": timezone.now().date(),
                "subject": "Ответ на заявление Иванова И.И.",
                "counterparty": "Гражданин Иванов И.И.",
                "status": Correspondence.Status.SENT,
                "assignee": demo_user,
                "created_by": admin_user,
                "linked_incoming": in_corr,
                "case": case_objs[0],
            },
        )

        PrintTemplate.objects.get_or_create(
            subsystem=subsystem,
            code="cover_in",
            defaults={
                "name": "Обложка входящего",
                "body": "Входящий № {{reg_number}} от {{reg_date}}\nТема: {{subject}}\nОт: {{counterparty}}\nСтатус: {{status}}",
                "is_active": True,
            },
        )

        SLARule.objects.update_or_create(
            subsystem=subsystem,
            code="default",
            defaults={
                "name": "Стандартный SLA пилота",
                "case_kind": "default",
                "hours_limit": 72,
                "escalate_to": mgr_user,
                "is_active": True,
            },
        )
        CaseRegulation.objects.get_or_create(
            subsystem=subsystem,
            code="citizen_30",
            defaults={
                "name": "Обращение гражданина — 30 раб. дней",
                "default_working_days": 30,
                "applies_on_status": CaseFile.Status.IN_PROGRESS,
                "notes": "Демо-регламент M36",
            },
        )
        tpl, _ = BPMTemplate.objects.update_or_create(
            subsystem=subsystem,
            code="approval",
            defaults={
                "name": "Согласование документа",
                "description": "Двухэтапное согласование: специалист → руководитель",
                "is_active": True,
                "steps": [
                    {"id": "s1", "name": "Специалист", "assignee_id": demo_user.id},
                    {"id": "s2", "name": "Руководитель", "assignee_id": mgr_user.id},
                ],
            },
        )
        if not case_objs[1].bpm_instances.exists():
            bpm.start_process(tpl, case_objs[1], admin_user)

        from delayu.services import archive as arch_svc

        demo_arch = case_objs[2]
        if not demo_arch.is_archived:
            arch_svc.archive_case(
                demo_arch,
                admin_user,
                reason="Демонстрация раздела M06 «Архив дел».",
                retention_years=10,
            )

        KnowledgeArticle.objects.get_or_create(
            subsystem=subsystem,
            title="Регламент регистрации входящих",
            defaults={
                "body": "Входящая корреспонденция регистрируется в день поступления. Срок ответа — 30 дней.",
                "tags": "регламент,сэд",
                "is_published": True,
            },
        )
        from delayu.models import AiPolicy, AudioArchiveItem

        AiPolicy.objects.get_or_create(
            subsystem=subsystem,
            defaults={"model_name": "demo-local", "max_requests_per_day": 500},
        )
        if case_objs and not AudioArchiveItem.objects.filter(subsystem=subsystem).exists():
            AudioArchiveItem.objects.create(
                subsystem=subsystem,
                case=case_objs[0],
                title="Запись совещания по делу",
                source_type=AudioArchiveItem.SourceType.MEETING,
                duration_sec=420,
                transcript="[Демо] Обсудили сроки и комплект документов.",
                recorded_at=timezone.now(),
                created_by=admin_user,
            )
            AudioArchiveItem.objects.create(
                subsystem=subsystem,
                case=case_objs[0],
                title="Входящий звонок гражданина",
                source_type=AudioArchiveItem.SourceType.CALL,
                duration_sec=180,
                recorded_at=timezone.now(),
                created_by=demo_user,
            )

        from delayu.services.nsi_choices import sync_classifiers_for_subsystem

        sync_classifiers_for_subsystem(subsystem)

        from delayu.models import (
            BulkOperation,
            ExportJob,
            FormSchema,
            ManagementDirective,
        )

        FormSchema.objects.update_or_create(
            subsystem=subsystem,
            target=FormSchema.Target.CASE,
            code="case_extra",
            defaults={
                "name": "Доп. поля дела",
                "schema": [
                    {"key": "source", "label": "Источник", "type": "text"},
                    {"key": "priority_note", "label": "Примечание", "type": "textarea"},
                ],
                "is_active": True,
            },
        )
        rt_emp = RegistryType.objects.filter(subsystem=subsystem, code="employees").first()
        if rt_emp:
            FormSchema.objects.update_or_create(
                subsystem=subsystem,
                target=FormSchema.Target.REGISTRY,
                code="employees",
                defaults={
                    "name": "Сотрудники (M74)",
                    "schema": rt_emp.field_schema or [],
                    "is_active": True,
                },
            )
            from delayu.services.form_schemas import sync_registry_form_schema

            fs = FormSchema.objects.get(
                subsystem=subsystem, target=FormSchema.Target.REGISTRY, code="employees"
            )
            sync_registry_form_schema(fs)
        if case_objs and not BulkOperation.objects.filter(subsystem=subsystem).exists():
            BulkOperation.objects.create(
                subsystem=subsystem,
                user=admin_user,
                operation=BulkOperation.Operation.STATUS,
                filter_params={"status": CaseFile.Status.NEW},
                payload={"new_status": CaseFile.Status.IN_PROGRESS},
                status=BulkOperation.Status.SUCCESS,
                affected_count=1,
                log="Демо: переведено 1 дело в «В работе».",
            )
        ExportJob.objects.get_or_create(
            subsystem=subsystem,
            user=admin_user,
            kind="cases_csv",
            title="Реестр дел (демо)",
            defaults={
                "status": ExportJob.Status.SUCCESS,
                "records_count": len(case_objs),
                "finished_at": timezone.now(),
            },
        )
        ManagementDirective.objects.update_or_create(
            subsystem=subsystem,
            number="ПР-2026-001",
            defaults={
                "title": "Подготовить сводку по пилотным делам",
                "instruction": "Сформировать отчёт до конца недели.",
                "assignee": demo_user,
                "author": mgr_user,
                "case": case_objs[0] if case_objs else None,
                "due_date": timezone.now().date() + timedelta(days=7),
                "status": ManagementDirective.Status.IN_PROGRESS,
            },
        )

        from delayu.models import ApiClientKey, IntegrationMessage
        from delayu.services.integrations import create_api_key, enqueue_outbound, process_outbound, receive_inbound

        smev_ep, _ = IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="smev_demo",
            defaults={
                "name": "СМЭВ (демо)",
                "endpoint_type": IntegrationEndpoint.EndpointType.SMEV,
                "description": "Межведомственный шлюз pilot",
                "config": {"url": "https://demo.local/smev", "simulate_fail": False},
                "is_active": True,
            },
        )
        IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="rest_internal",
            defaults={
                "name": "Внутренний REST",
                "endpoint_type": IntegrationEndpoint.EndpointType.REST,
                "config": {"base_url": "/api/v1/"},
                "is_active": True,
            },
        )
        ext_1c, _ = IntegrationEndpoint.objects.update_or_create(
            subsystem=subsystem,
            code="erp_1c",
            defaults={
                "name": "1С:ERP",
                "endpoint_type": IntegrationEndpoint.EndpointType.EXTERNAL_1C,
                "config": {
                    "field_mapping": {
                        "CaseFile.number": "ExternalDocNo",
                        "CaseFile.title": "Subject",
                    }
                },
                "is_active": True,
            },
        )
        if not ApiClientKey.objects.filter(subsystem=subsystem).exists():
            create_api_key(subsystem=subsystem, name="Демо-ключ pilot", rate_limit=5000)
        if not IntegrationMessage.objects.filter(endpoint=smev_ep).exists():
            m_out = enqueue_outbound(smev_ep, {"message_type": "Request", "demo": True})
            process_outbound(m_out)
            receive_inbound(smev_ep, {"message_type": "Response", "status": "OK"})
            m_ext = enqueue_outbound(ext_1c, {"entity": "CaseFile", "external_id": "1C-999"})
            process_outbound(m_ext)

        ReportTemplate.objects.update_or_create(
            subsystem=subsystem,
            code="cases",
            defaults={
                "name": "Сводка по делам",
                "query_key": "cases_summary",
                "columns": ["status", "cnt"],
                "report_kind": ReportTemplate.ReportKind.STANDARD,
                "description": "Агрегация дел по статусам",
            },
        )
        ReportTemplate.objects.update_or_create(
            subsystem=subsystem,
            code="tasks_load",
            defaults={
                "name": "Нагрузка по задачам",
                "query_key": "tasks_by_user",
                "columns": [],
                "report_kind": ReportTemplate.ReportKind.STANDARD,
            },
        )
        ReportTemplate.objects.update_or_create(
            subsystem=subsystem,
            code="cases_trend",
            defaults={
                "name": "Динамика дел",
                "query_key": "cases_trend",
                "report_kind": ReportTemplate.ReportKind.CHART,
                "default_period_days": 30,
            },
        )
        RegulatoryReportSubmission.objects.get_or_create(
            subsystem=subsystem,
            form_code="omsu-01",
            period_label="2026-Q1",
            version=1,
            defaults={
                "form_name": "Сводка обращений граждан (демо)",
                "period_start": timezone.now().date().replace(month=1, day=1),
                "period_end": timezone.now().date().replace(month=3, day=31),
                "indicators": {"appeals_received": 120, "cases_closed": 95},
                "status": RegulatoryReportSubmission.Status.DRAFT,
            },
        )
        head_pos = Position.objects.filter(department=dept, code="head").first()
        if head_pos:
            UserAssignment.objects.get_or_create(
                user=mgr_user, department=dept, position=head_pos
            )

        room, _ = ChatRoom.objects.get_or_create(
            subsystem=subsystem, name="Общий чат", defaults={"case": case_objs[0]}
        )
        room.members.add(admin_user, demo_user, mgr_user)

        from delayu.services.comms import create_comment, post_chat_message
        from django.utils import timezone as tz

        if not Comment.objects.filter(case=case_objs[0]).exists():
            create_comment(
                subsystem=subsystem,
                author=admin_user,
                body="Прошу согласовать до пятницы. @demo",
                case=case_objs[0],
            )
        post_chat_message(
            room=room,
            author=demo_user,
            body="Коллеги, материалы по делу загружены. @manager",
        )
        ObjectSubscription.objects.get_or_create(
            user=mgr_user,
            subsystem=subsystem,
            target_type=ObjectSubscription.TargetType.CASE,
            case=case_objs[0],
        )
        VideoMeeting.objects.get_or_create(
            subsystem=subsystem,
            title="Совещание по PILOT-2026-0001",
            defaults={
                "meeting_url": "https://meet.example.local/pilot-0001",
                "scheduled_at": tz.now() + timedelta(days=2),
                "case": case_objs[0],
                "created_by": mgr_user,
                "protocol_notes": "Демо-протокол M40",
            },
        )
        MessengerChannel.objects.get_or_create(
            subsystem=subsystem,
            code="telegram_ops",
            defaults={
                "name": "Telegram — операционный чат",
                "channel_type": MessengerChannel.ChannelType.TELEGRAM,
                "webhook_url": "https://api.telegram.org/bot/demo/webhook",
                "is_active": True,
                "notes": "Демо M41, без реальной отправки",
            },
        )

        for user, level, title in (
            (demo_user, Notification.Level.INFO, "Добро пожаловать в ДелаЮ"),
            (demo_user, Notification.Level.WARNING, "Просрочена задача по делу"),
            (mgr_user, Notification.Level.URGENT, "Требуется согласование"),
        ):
            Notification.objects.get_or_create(
                user=user,
                subsystem=subsystem,
                title=title,
                defaults={
                    "body": "Демо-уведомление модуля M12.",
                    "link": "/workspace/today/",
                    "level": level,
                },
            )

        Favorite.objects.get_or_create(
            user=demo_user,
            subsystem=subsystem,
            label="Мне на сегодня",
            defaults={"url_path": "/workspace/today/", "icon_class": "ri-calendar-check-line"},
        )
        Favorite.objects.get_or_create(
            user=demo_user,
            subsystem=subsystem,
            label="Реестр дел",
            defaults={"url_path": "/cases/", "icon_class": "ri-folder-line", "sort_order": 1},
        )
        SavedFilter.objects.get_or_create(
            user=demo_user,
            subsystem=subsystem,
            module_code="M22",
            name="Дела в работе",
            defaults={"params": {"status": "in_progress"}},
        )

        ActivityEvent.objects.get_or_create(
            subsystem=subsystem,
            actor=admin_user,
            verb="загрузил демо-данные",
            target_repr="Пилотная подсистема",
            defaults={"module_code": "M01", "link_path": "/"},
        )
        ActivityEvent.objects.get_or_create(
            subsystem=subsystem,
            actor=demo_user,
            verb="открыл кабинет",
            target_repr="Личный кабинет",
            defaults={"module_code": "M07", "link_path": "/workspace/cabinet/"},
        )

        from decimal import Decimal

        from delayu.models import (
            CitizenAppeal,
            DataDataset,
            EtlJob,
            EtlRun,
            GeoLayer,
            GeoObject,
            PwaDevice,
            PwaDraft,
            SsoProvider,
        )

        layer_addr, _ = GeoLayer.objects.update_or_create(
            subsystem=subsystem,
            code="addresses",
            defaults={"name": "Адреса обращений", "color": "#28c76f", "is_visible": True},
        )
        layer_obj, _ = GeoLayer.objects.update_or_create(
            subsystem=subsystem,
            code="objects",
            defaults={"name": "Объекты учёта", "color": "#666cff", "is_visible": True},
        )
        if case_objs and not GeoObject.objects.filter(subsystem=subsystem).exists():
            GeoObject.objects.create(
                subsystem=subsystem,
                layer=layer_addr,
                case=case_objs[0],
                title="Адрес заявителя PILOT",
                address="ул. Пилотная, 1",
                latitude=Decimal("55.751244"),
                longitude=Decimal("37.618423"),
            )
            GeoObject.objects.create(
                subsystem=subsystem,
                layer=layer_obj,
                case=case_objs[1] if len(case_objs) > 1 else case_objs[0],
                title="Объект проверки",
                address="пр. Демонстрационный, 10",
                latitude=Decimal("55.760000"),
                longitude=Decimal("37.630000"),
            )
        pwa_dev, _ = PwaDevice.objects.get_or_create(
            subsystem=subsystem,
            user=demo_user,
            device_label="Планшет полевой (демо)",
            defaults={"app_version": "1.0.0-pilot", "last_sync_at": timezone.now()},
        )
        PwaDraft.objects.get_or_create(
            device=pwa_dev,
            title="Осмотр объекта — черновик",
            defaults={
                "payload": {"case_number": "PILOT-2026-0001", "notes": "Фото загружены офлайн"},
            },
        )
        SsoProvider.objects.update_or_create(
            subsystem=subsystem,
            name="ЕСИА (демо)",
            defaults={
                "provider_type": SsoProvider.ProviderType.ESIA,
                "client_id": "esia-demo-client",
                "is_active": True,
                "metadata": {
                    "demo": True,
                    "demo_username": "admin",
                    "auth_url": "https://esia.gosuslugi.ru/demo",
                },
            },
        )
        etl_job, _ = EtlJob.objects.update_or_create(
            subsystem=subsystem,
            name="Импорт реестра граждан",
            defaults={
                "source_type": EtlJob.SourceType.CSV,
                "schedule_cron": "0 2 * * *",
                "is_active": True,
            },
        )
        if not etl_job.runs.exists():
            EtlRun.objects.create(
                job=etl_job,
                status=EtlRun.Status.SUCCESS,
                rows_ok=128,
                rows_err=2,
                log="Демо-загрузка CSV завершена.",
                finished_at=timezone.now(),
            )
        DataDataset.objects.update_or_create(
            subsystem=subsystem,
            slug="cases_analytics",
            defaults={
                "name": "Дела для аналитики",
                "description": "Агрегат карточек дел для BI",
                "is_published": True,
                "row_count": len(case_objs),
                "schema": {"fields": ["number", "status", "due_date"]},
            },
        )
        CitizenAppeal.objects.update_or_create(
            subsystem=subsystem,
            public_id="GR-2026-00042",
            defaults={
                "applicant_name": "Иванов И.И.",
                "subject": "Жалоба на срок рассмотрения обращения",
                "status": CitizenAppeal.Status.IN_PROGRESS,
                "case": case_objs[0] if case_objs else None,
            },
        )

        from delayu.models import (
            AvScanResult,
            BackupRecord,
            MarketplaceConnector,
            NotificationTemplate,
            OnboardingArticle,
            UserDashboardLayout,
        )
        from delayu.services.exploitation import demo_scan_file, get_or_create_pii_policy, run_demo_backup

        NotificationTemplate.objects.update_or_create(
            subsystem=subsystem,
            event_code="case_assigned",
            channel=NotificationTemplate.Channel.IN_APP,
            defaults={
                "subject": "Назначено дело",
                "body": "Вам назначено дело {case}. {link}",
                "is_active": True,
            },
        )
        NotificationTemplate.objects.update_or_create(
            subsystem=subsystem,
            event_code="task_overdue",
            channel=NotificationTemplate.Channel.EMAIL,
            defaults={
                "subject": "Просрочена задача",
                "body": "Исполнитель {user}: просрочена задача по делу {case}.",
                "is_active": True,
            },
        )
        mail_events = [
            (
                "bpm_step_assigned",
                "Новое согласование: {step_name}",
                "Вам назначен шаг «{step_name}» по делу {case}. {link}",
            ),
            (
                "bpm_completed",
                "Согласование завершено",
                "Процесс по делу {case} успешно завершён. {link}",
            ),
            (
                "bpm_rejected",
                "Согласование отклонено",
                "Процесс по делу {case} отклонён. {link}",
            ),
            (
                "corr_routed",
                "Корреспонденция {reg_number}",
                "Вам передано: {subject}. От: {user}. {comment} {link}",
            ),
            (
                "corr_workflow_complete",
                "Маршрут завершён: {reg_number}",
                "Документ «{subject}» закрыт. Исполнитель: {user}. {link}",
            ),
        ]
        for code, subject, body in mail_events:
            NotificationTemplate.objects.update_or_create(
                subsystem=subsystem,
                event_code=code,
                channel=NotificationTemplate.Channel.EMAIL,
                defaults={"subject": subject, "body": body, "is_active": True},
            )
            NotificationTemplate.objects.update_or_create(
                subsystem=subsystem,
                event_code=code,
                channel=NotificationTemplate.Channel.IN_APP,
                defaults={"subject": subject, "body": body, "is_active": True},
            )
        policy = get_or_create_pii_policy(subsystem)
        policy.masked_roles = ["viewer"]
        policy.demo_mode = True
        policy.save()
        if not BackupRecord.objects.filter(subsystem=subsystem).exists():
            run_demo_backup(subsystem, "Полный бэкап pilot")
        doc = DocumentFile.objects.filter(subsystem=subsystem).first()
        if doc and not AvScanResult.objects.filter(subsystem=subsystem).exists():
            demo_scan_file(
                subsystem=subsystem,
                filename=doc.file.name if doc.file else doc.title,
                document=doc,
            )

        OnboardingArticle.objects.update_or_create(
            slug="welcome-tour",
            defaults={
                "subsystem": subsystem,
                "title": "Добро пожаловать в ДелаЮ",
                "body": "Пройдите тур: дела → документы → согласования.",
                "kind": OnboardingArticle.Kind.TOUR,
                "sort_order": 1,
                "is_published": True,
            },
        )
        UserDashboardLayout.objects.get_or_create(
            user=admin_user,
            subsystem=subsystem,
            name="Руководитель",
            defaults={
                "widgets": [
                    {"id": "kpi_cases", "title": "Дела", "col": 4},
                    {"id": "kpi_tasks", "title": "Задачи", "col": 4},
                    {"id": "chart_status", "title": "Статусы", "col": 4},
                ],
                "is_default": True,
            },
        )
        for code, name, vendor, mods in (
            ("smev_adapter", "СМЭВ 3.0", "ГосТех", ["M44"]),
            ("1c_erp", "1С:ERP", "1С", ["M45"]),
            ("telegram_bot", "Telegram Bot", "Open Source", ["M41"]),
        ):
            MarketplaceConnector.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "vendor": vendor,
                    "description": f"Адаптер для модулей {', '.join(mods)}",
                    "module_codes": mods,
                    "is_certified": code == "smev_adapter",
                    "install_count": 3 if code == "1c_erp" else 0,
                },
            )

        self.stdout.write(self.style.SUCCESS("Полный набор демо-данных загружен (admin/admin, demo/demo, manager/manager)"))
