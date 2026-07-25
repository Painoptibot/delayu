"""Демо-данные инвестконтура Краснодарского края."""
from datetime import date
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import connection

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_invest import (
    InvestHandoff,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestSite,
    InvestSmevRequest,
)
from delayu.services.invest_booking import book_site
from delayu.services.invest_handoff import request_handoff
from delayu.services.invest_package import ensure_package
from delayu.services.invest_roadmap import seed_support_roadmap
from delayu.services.invest_roles import INVEST_MODULE_CODES, ROLE_SPECS, perm_for_role

User = get_user_model()


class Command(BaseCommand):
    help = "Создаёт подсистему invest-kk, роли, пользователей и демо-данные"

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

        subsystem, created = Subsystem.objects.update_or_create(
            code="invest-kk",
            defaults={
                "name": "Инвестконтур Краснодарского края",
                "description": "Демо-контур привлечения и сопровождения инвестпроектов Кубани",
                "status": Subsystem.Status.ACTIVE,
                "primary_color": "#0f766e",
                "industry_template": "invest",
            },
        )
        action = "Создана" if created else "Обновлена"
        self.stdout.write(f"{action} подсистема: {subsystem.name}")

        self._enable_modules(subsystem)
        orgs = self._seed_orgs(subsystem)
        roles = self._seed_roles(subsystem)
        users = self._seed_users(subsystem, orgs, roles)
        self._seed_demo(subsystem, orgs, users)
        from delayu.services.invest_flags import ensure_automation_config

        ensure_automation_config(subsystem)

        self.stdout.write(self.style.SUCCESS("Инвестконтур Кубани развёрнут (code=invest-kk)"))
        self.stdout.write("  invest_admin / invest_admin — администратор")
        self.stdout.write("  invest_agency / invest_agency — агентство")
        self.stdout.write("  invest_dept / invest_dept — департамент")
        self.stdout.write("  invest_mo / invest_mo — муниципалитет")
        self.stdout.write("  invest_viewer / invest_viewer — наблюдатель")

    def _enable_modules(self, subsystem):
        enabled = set(INVEST_MODULE_CODES)
        entitlement_model = self._license_entitlement_model()
        for mod in ModuleCatalog.objects.all():
            SubsystemModule.objects.update_or_create(
                subsystem=subsystem,
                module=mod,
                defaults={"enabled": mod.code in enabled},
            )
            if mod.code in enabled and entitlement_model is not None:
                entitlement_model.objects.update_or_create(
                    subsystem=subsystem, module=mod, defaults={"valid_until": None}
                )

    def _license_entitlement_model(self):
        try:
            return apps.get_model("delayu", "LicenseEntitlement")
        except LookupError:
            return None

    def _seed_orgs(self, subsystem):
        specs = (
            ("dept", "Департамент"),
            ("agency", "Агентство"),
            ("mo-krasnodar", "МО Краснодар"),
            ("mo-sochi", "МО Сочи"),
        )
        orgs = {}
        for code, name in specs:
            orgs[code], _ = Organization.objects.update_or_create(
                subsystem=subsystem,
                code=code,
                defaults={"name": name, "is_active": True},
            )
        return orgs

    def _seed_roles(self, subsystem):
        roles = {}
        for code, meta in ROLE_SPECS.items():
            roles[code] = self._upsert_role(subsystem, code, meta)

        for role in roles.values():
            for mod in ModuleCatalog.objects.all():
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults=perm_for_role(role.code, mod.code),
                )
        return roles

    def _upsert_role(self, subsystem, code, meta):
        defaults = {
            "name": meta["label"],
            "description": "",
            "is_system": meta.get("system", False),
        }
        role = Role.objects.filter(subsystem=subsystem, code=code).first()
        if role:
            for field, value in defaults.items():
                setattr(role, field, value)
            role.save(update_fields=[*defaults.keys()])
            return role

        columns = {
            col.name for col in connection.introspection.get_table_description(connection.cursor(), Role._meta.db_table)
        }
        if "is_subsystem_admin" not in columns:
            return Role.objects.create(subsystem=subsystem, code=code, **defaults)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO delayu_role
                    (subsystem_id, code, name, description, is_system, parent_role_id, is_subsystem_admin)
                VALUES (%s, %s, %s, %s, %s, NULL, %s)
                RETURNING id
                """,
                [
                    subsystem.pk,
                    code,
                    defaults["name"],
                    defaults["description"],
                    defaults["is_system"],
                    code == "invest_admin",
                ],
            )
            role_id = cursor.fetchone()[0]
        return Role.objects.get(pk=role_id)

    def _seed_users(self, subsystem, orgs, roles):
        specs = (
            ("invest_admin", "Администратор", "Инвестконтур", "invest_admin", "dept"),
            ("invest_agency", "Анна", "Агентская", "invest_agency", "agency"),
            ("invest_dept", "Дмитрий", "Департаментский", "invest_dept", "dept"),
            ("invest_mo", "Мария", "Муниципальная", "invest_mo", "mo-krasnodar"),
            ("invest_viewer", "Виктор", "Наблюдатель", "invest_viewer", "agency"),
        )
        users = {}
        for username, first, last, role_code, org_code in specs:
            user, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "email": f"{username}@invest-kk.local",
                    "first_name": first,
                    "last_name": last,
                },
            )
            user.set_password(username)
            user.save(update_fields=["password", "email", "first_name", "last_name"])
            SubsystemMembership.objects.update_or_create(
                user=user,
                subsystem=subsystem,
                organization=orgs[org_code],
                role=roles[role_code],
                defaults={"is_default": True},
            )
            users[username] = user
        return users

    def _seed_demo(self, subsystem, orgs, users):
        InvestSmevRequest.objects.filter(subsystem=subsystem).delete()
        InvestHandoff.objects.filter(project__subsystem=subsystem).delete()
        InvestProjectSite.objects.filter(project__subsystem=subsystem).delete()
        InvestProject.objects.filter(subsystem=subsystem).delete()
        InvestSite.objects.filter(subsystem=subsystem).delete()

        projects = self._seed_projects(subsystem, orgs, users)
        sites = self._seed_sites(subsystem, orgs)

        book_site(project=projects["P-INV-001"], site=sites["23:43:0107001:101"], user=users["invest_agency"])
        InvestProjectSite.objects.update_or_create(
            project=projects["P-INV-002"],
            site=sites["23:49:0402002:88"],
            defaults={"role": InvestProjectSite.Role.PROPOSED},
        )
        InvestProjectSite.objects.update_or_create(
            project=projects["P-INV-001"],
            site=sites["23:43:0101001:77"],
            defaults={"role": InvestProjectSite.Role.CANDIDATE},
        )

        for project in (projects["P-INV-001"], projects["P-INV-002"]):
            pkg = ensure_package(project)
            if project.code == "P-INV-002":
                pkg.items.filter(code__in=("anketa", "protocol")).update(
                    status=InvestPackageItem.Status.ATTACHED
                )

        request_handoff(
            project=projects["P-INV-002"],
            user=users["invest_agency"],
            comment="Пакет собран частично, требуется проверка департамента.",
        )
        seed_support_roadmap(projects["P-SUP-001"])

    def _seed_projects(self, subsystem, orgs, users):
        specs = (
            {
                "code": "P-INV-001",
                "name": "Тепличный комплекс «Кубань Агро»",
                "organization": orgs["mo-krasnodar"],
                "investor_name": "ООО «Кубань Агро Инвест»",
                "industry": "АПК",
                "description": "Строительство тепличного комплекса пятого поколения с логистическим хабом.",
                "funnel": InvestProject.Funnel.ATTRACTION,
                "stage": "site_pick",
                "owner": users["invest_agency"],
                "contact_person": "Иванова М.А.",
                "contact_phone": "+7 (861) 200-11-22",
                "contact_email": "ivanova@kuban-agro.example",
                "investment_amount": Decimal("1250.00"),
                "jobs_count": 180,
                "support_measures": "Льготный земельный участок, сопровождение по инфраструктуре.",
                "planned_start": date(2026, 9, 1),
                "planned_end": date(2028, 6, 30),
            },
            {
                "code": "P-INV-002",
                "name": "Гостиничный комплекс в Сочи",
                "organization": orgs["mo-sochi"],
                "investor_name": "ООО «Юг Девелопмент»",
                "industry": "Туризм",
                "description": "Гостиничный комплекс 4* с конференц-залом и SPA.",
                "funnel": InvestProject.Funnel.ATTRACTION,
                "stage": "package_ready",
                "owner": users["invest_agency"],
                "contact_person": "Петров С.В.",
                "contact_phone": "+7 (862) 555-01-01",
                "contact_email": "petrov@yug-dev.example",
                "investment_amount": Decimal("3400.00"),
                "jobs_count": 260,
                "support_measures": "Сопровождение по подключению сетей, консультации по ВРИ.",
                "planned_start": date(2027, 3, 1),
                "planned_end": date(2029, 12, 31),
            },
            {
                "code": "P-SUP-001",
                "name": "Индустриальный парк «Краснодар Восточный»",
                "organization": orgs["mo-krasnodar"],
                "investor_name": "АО «Индустрия Кубани»",
                "industry": "Промышленность",
                "description": "Индустриальный парк с готовой инфраструктурой для резидентов.",
                "funnel": InvestProject.Funnel.SUPPORT,
                "stage": "accepted",
                "owner": users["invest_dept"],
                "contact_person": "Сидорова Е.Н.",
                "contact_phone": "+7 (861) 300-44-55",
                "contact_email": "sidorova@industry-kk.example",
                "investment_amount": Decimal("5800.00"),
                "jobs_count": 520,
                "support_measures": "Дорожная карта сопровождения, SLA по разрешениям.",
                "planned_start": date(2026, 4, 1),
                "planned_end": date(2030, 12, 31),
                "municipality_notes": "МО готово ускорить согласование ЗУ при подтверждении ВРИ.",
            },
        )
        projects = {}
        for spec in specs:
            project = InvestProject.objects.create(subsystem=subsystem, **spec)
            projects[project.code] = project
        return projects

    def _seed_sites(self, subsystem, orgs):
        specs = (
            {
                "cadastral_number": "23:43:0107001:101",
                "name": "Площадка «Краснодар Восток»",
                "organization": orgs["mo-krasnodar"],
                "address": "г. Краснодар, восточная промзона",
                "area_ha": Decimal("18.5000"),
                "land_category": "Земли промышленности",
                "vri": "Производственная деятельность",
                "right_type": "аренда",
                "encumbrances": "",
                "zone_info": "Без критичных пересечений ООПТ",
                "status": InvestSite.Status.ACTUAL,
                "completeness_pct": 92,
                "latitude": Decimal("45.035470"),
                "longitude": Decimal("39.061120"),
            },
            {
                "cadastral_number": "23:49:0402002:88",
                "name": "Площадка «Сочи Логистика»",
                "organization": orgs["mo-sochi"],
                "address": "г. Сочи, Адлерский район",
                "area_ha": Decimal("6.2500"),
                "land_category": "Земли населённых пунктов",
                "vri": "Гостиничное обслуживание",
                "right_type": "собственность субъекта РФ",
                "status": InvestSite.Status.ACTUAL,
                "completeness_pct": 86,
                "latitude": Decimal("43.602810"),
                "longitude": Decimal("39.734150"),
            },
            {
                "cadastral_number": "23:43:0112005:44",
                "name": "Площадка «Агро Юг»",
                "organization": orgs["mo-krasnodar"],
                "address": "МО г. Краснодар, южный сектор",
                "area_ha": Decimal("42.0000"),
                "land_category": "Земли сельхозназначения",
                "vri": "Сельскохозяйственное производство",
                "right_type": "аренда",
                "status": InvestSite.Status.IN_REVIEW,
                "completeness_pct": 74,
                "latitude": Decimal("45.091210"),
                "longitude": Decimal("38.912430"),
            },
            {
                "cadastral_number": "23:49:0301007:12",
                "name": "Площадка «Горный кластер»",
                "organization": orgs["mo-sochi"],
                "address": "г. Сочи, Красная Поляна",
                "area_ha": Decimal("11.8000"),
                "land_category": "Земли особо охраняемых территорий",
                "vri": "Туристическое обслуживание",
                "right_type": "постоянное пользование",
                "status": InvestSite.Status.ACTUAL,
                "completeness_pct": 80,
                "latitude": Decimal("43.679920"),
                "longitude": Decimal("40.205880"),
            },
            {
                # Черновик для демо СМЭВ: только кадастр → «Запросить ЕГРН» → «Применить»
                "cadastral_number": "23:43:0101001:77",
                "name": "ЗУ под автозаполнение СМЭВ (демо)",
                "organization": orgs["mo-krasnodar"],
                "status": InvestSite.Status.DRAFT,
                "completeness_pct": 15,
            },
        )
        sites = {}
        for spec in specs:
            site = InvestSite.objects.create(subsystem=subsystem, **spec)
            sites[site.cadastral_number] = site
        return sites
