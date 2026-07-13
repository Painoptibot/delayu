"""Демо-данные «Топливный пропуск — Новороссийск»."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from delayu.models import (
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)
from delayu.models_fuel import FuelApplication, FuelAzsStation, FuelCategory, FuelCitizen
from delayu.services.users import get_or_create_profile

User = get_user_model()


class Command(BaseCommand):
    help = "Подсистема fuel/novorossiysk и справочники для портала граждан"

    def handle(self, *args, **options):
        from django.core.management import call_command

        call_command("seed_catalog", verbosity=0)

        subsystem, created = Subsystem.objects.update_or_create(
            code="novorossiysk",
            defaults={
                "name": "Новороссийск — топливный пропуск",
                "description": "Пилот «Топливный пропуск» для администрации Новороссийска",
                "status": Subsystem.Status.ACTIVE,
                "primary_color": "#2563eb",
                "industry_template": "fuel",
                "public_subdomain": "novorossiysk",
            },
        )
        action = "Создана" if created else "Обновлена"
        self.stdout.write(f"{action} подсистема: {subsystem.name}")

        for code in ("M01", "M02", "M03", "M07", "M15", "M22", "M43", "M68", "M72"):
            mod = ModuleCatalog.objects.filter(code=code).first()
            if mod:
                SubsystemModule.objects.update_or_create(
                    subsystem=subsystem, module=mod, defaults={"enabled": True}
                )

        categories = [
            ("I", "Критическая инфраструктура", 500, False, 1),
            ("II", "ЖКХ и транспорт", 150, True, 2),
            ("III", "Такси и доставка", 40, True, 3),
            ("IV", "Предприятия", 80, True, 4),
            ("V", "Население", 30, False, 5),
        ]
        for code, name, limit, mod, sort in categories:
            FuelCategory.objects.update_or_create(
                subsystem=subsystem,
                code=code,
                defaults={
                    "name": name,
                    "daily_limit_liters": limit,
                    "requires_moderation": mod,
                    "sort_order": sort,
                },
            )

        # Реальные АЗС Новороссийска (адреса по 2ГИС, Яндекс.Карты, сайты сетей)
        azs_data = [
            (
                "lukoil-dzerzh-211",
                "Лукойл, пр. Дзержинского, 211/1",
                "Лукойл",
                "пр. Дзержинского, 211/1",
                "Восточный",
                "44.681190",
                "37.780152",
                FuelAzsStation.Status.OK,
                4200,
                12,
                True,
                "lukoildzerzh211",
            ),
            (
                "lukoil-dzerzh-188",
                "Лукойл, пр. Дзержинского, 188Б",
                "Лукойл",
                "пр. Дзержинского, 188Б",
                "Восточный",
                "44.686533",
                "37.780041",
                FuelAzsStation.Status.BUSY,
                1800,
                35,
                True,
                "lukoildzerzh188",
            ),
            (
                "lukoil-dzerzh-xvor",
                "Лукойл, пр. Дзержинского / ул. Хворостянского",
                "Лукойл",
                "пр. Дзержинского (пересечение с ул. Хворостянского)",
                "Восточный",
                "44.680708",
                "37.783264",
                FuelAzsStation.Status.OK,
                5100,
                8,
                True,
                "lukoildzerzh",
            ),
            (
                "lukoil-suvorov-54",
                "Лукойл, ул. Суворовская, 54",
                "Лукойл",
                "ул. Суворовская, 54",
                "Центральный",
                "44.694610",
                "37.787784",
                FuelAzsStation.Status.OK,
                3600,
                15,
                True,
                "lukoilsuvorov54",
            ),
            (
                "lukoil-suhum-srz",
                "Лукойл, Сухумское шоссе, 64Б",
                "Лукойл",
                "Сухумское шоссе, 64Б (район СРЗ)",
                "Восточный",
                "44.732425",
                "37.809460",
                FuelAzsStation.Status.LOW,
                900,
                22,
                True,
                "lukoilsuhumsrz",
            ),
            (
                "rosneft-suhum-57",
                "Роснефть, Сухумское шоссе, 57А",
                "Роснефть",
                "Сухумское шоссе, 57А",
                "Южный",
                "44.718274",
                "37.836768",
                FuelAzsStation.Status.OK,
                4800,
                18,
                True,
                "rosneftsuhum57",
            ),
            (
                "rosneft-suhum-64",
                "Роснефть, Сухумское шоссе, 64Б",
                "Роснефть",
                "Сухумское шоссе, 64Б",
                "Южный",
                "44.732342",
                "37.809496",
                FuelAzsStation.Status.OK,
                3900,
                10,
                True,
                "rosneftsuhum64",
            ),
            (
                "rosneft-lenina-2",
                "Роснефть, п. Цемдолина, ул. Ленина, 2",
                "Роснефть",
                "п. Цемдолина, ул. Ленина, 2",
                "Северный",
                "44.750513",
                "37.727361",
                FuelAzsStation.Status.OK,
                5500,
                5,
                True,
                "rosneftlenina2",
            ),
            (
                "rosneft-kunikova",
                "Роснефть, ул. Куникова, 47А/1",
                "Роснефть",
                "ул. Куникова, 47А/1",
                "Центральный",
                "44.693470",
                "37.769817",
                FuelAzsStation.Status.BUSY,
                2100,
                42,
                False,
                "rosneftkunikova",
            ),
            (
                "gazprom-myskhak",
                "Газпром, Мысхакское шоссе, 53Б",
                "Газпром",
                "Мысхакское шоссе, 53Б",
                "Приморский",
                "44.698680",
                "37.765769",
                FuelAzsStation.Status.OK,
                3300,
                14,
                True,
                "gazprommyskhak",
            ),
            (
                "gazprom-natuh",
                "Газпром, ст. Натухаевская",
                "Газпром",
                "ст. Натухаевская, ул. Ленина",
                "Северный",
                "44.7480",
                "37.7420",
                FuelAzsStation.Status.LOW,
                700,
                28,
                True,
                "gazpromnatuh",
            ),
            (
                "tatneft-verhbak",
                "Татнефть, п. Верхнебаканский",
                "Татнефть",
                "п. Верхнебаканский, ул. Мира",
                "Северный",
                "44.7850",
                "37.8350",
                FuelAzsStation.Status.OK,
                4100,
                7,
                True,
                "tatneftverhbak",
            ),
            (
                "ufim-malozem",
                "УФИМ-Нефть, ул. Малоземельская",
                "УФИМ-Нефть",
                "ул. Малоземельская",
                "Центральный",
                "44.686960",
                "37.769262",
                FuelAzsStation.Status.OK,
                2800,
                11,
                True,
                "ufimmalozem",
            ),
            (
                "lukoil-lenina-7",
                "Лукойл, ул. Ленина, 7А",
                "Лукойл",
                "п. Цемдолина, ул. Ленина, 7А",
                "Северный",
                "44.745656",
                "37.726320",
                FuelAzsStation.Status.OK,
                4600,
                9,
                True,
                "lukoillenina7",
            ),
            (
                "rosneft-zolryb",
                "АЗС, ул. Золотая Рыбка, 11/1",
                "Роснефть",
                "ул. Золотая Рыбка, 11/1",
                "Приморский",
                "44.784152",
                "37.681602",
                FuelAzsStation.Status.OK,
                3400,
                16,
                True,
                "rosneftzolryb",
            ),
            (
                "lukoil-glebovka",
                "Лукойл, пос. Глебовка",
                "Лукойл",
                "пос. Глебовка, ул. Приморская",
                "Приморский",
                "44.7520",
                "37.7980",
                FuelAzsStation.Status.OK,
                3700,
                6,
                True,
                "lukoiglebovka",
            ),
            (
                "rosneft-dzerzh-227",
                "Роснефть, пр. Дзержинского, 227",
                "Роснефть",
                "пр. Дзержинского, 227",
                "Восточный",
                "44.675361",
                "37.779480",
                FuelAzsStation.Status.EMPTY,
                0,
                0,
                False,
                "rosneftdzerzh227",
            ),
            (
                "gazprom-rail",
                "Газпром, Железнодорожная петля, 10",
                "Газпром",
                "Железнодорожная петля, 10",
                "Восточный",
                "44.692800",
                "37.754200",
                FuelAzsStation.Status.OK,
                2900,
                20,
                True,
                "gazpromrail",
            ),
            (
                "gazpromneft-gayduk",
                "Газпромнефть, с. Гайдук",
                "Газпромнефть",
                "с. Гайдук, трасса Новороссийск — Керчь, 8 км",
                "Приморский",
                "44.773300",
                "37.694990",
                FuelAzsStation.Status.OK,
                3200,
                13,
                True,
                "gazpromnftgayduk",
            ),
            (
                "lukoil-raevskaya",
                "Лукойл, ст. Раевская",
                "Лукойл",
                "ст. Раевская, ул. Красная",
                "Северный",
                "44.7650",
                "37.7880",
                FuelAzsStation.Status.LOW,
                1100,
                25,
                True,
                "lukoilraevskaya",
            ),
        ]
        new_codes = {row[0] for row in azs_data}
        from delayu.models_fuel import FuelRedeem, FuelRedeemAttempt

        subsystem.fuel_applications.all().delete()
        FuelRedeem.objects.filter(subsystem=subsystem).delete()
        FuelRedeemAttempt.objects.filter(subsystem=subsystem).delete()
        old_stations = subsystem.fuel_azs_stations.exclude(code__in=new_codes)
        removed, _ = old_stations.delete()
        if removed:
            self.stdout.write(f"Удалено устаревших АЗС: {removed}")

        for (
            code,
            name,
            network,
            address,
            district,
            lat,
            lng,
            status,
            stock,
            queue,
            accepting,
            portal_login,
        ) in azs_data:
            FuelAzsStation.objects.update_or_create(
                subsystem=subsystem,
                code=code,
                defaults={
                    "name": name,
                    "network": network,
                    "address": address,
                    "district": district,
                    "latitude": lat,
                    "longitude": lng,
                    "status": status,
                    "stock_liters": stock,
                    "queue_minutes": queue,
                    "is_accepting_permits": accepting,
                    "portal_login": portal_login,
                    "portal_pin": "1234",
                },
            )
        self.stdout.write(f"АЗС в системе: {subsystem.fuel_azs_stations.count()}")

        self._seed_demo_applications(subsystem)
        self._seed_demo_blacklist(subsystem)
        self._seed_parity_rule(subsystem)
        self._seed_max_channel(subsystem)

        org, _ = Organization.objects.update_or_create(
            subsystem=subsystem, code="depttrans", defaults={"name": "Дептранс Новороссийска"}
        )
        role, _ = Role.objects.update_or_create(
            subsystem=subsystem,
            code="fuel_operator",
            defaults={"name": "Оператор топливного штаба", "is_system": True},
        )
        for mod_code in ("M22", "M15", "M07"):
            mod = ModuleCatalog.objects.filter(code=mod_code).first()
            if mod:
                RoleModulePermission.objects.update_or_create(
                    role=role,
                    module=mod,
                    defaults={
                        "can_view": True,
                        "can_create": True,
                        "can_change": True,
                        "can_delete": False,
                    },
                )
        op_user, created = User.objects.get_or_create(
            username="fuel_nvr",
            defaults={
                "email": "fuel@novorossiysk.local",
                "first_name": "Оператор",
                "last_name": "Штаба",
            },
        )
        if created:
            op_user.set_password("fuel_nvr")
            op_user.save()
        SubsystemMembership.objects.update_or_create(
            user=op_user,
            subsystem=subsystem,
            organization=org,
            role=role,
            defaults={"is_default": True},
        )
        profile = get_or_create_profile(op_user)
        profile.active_subsystem = subsystem
        profile.save(update_fields=["active_subsystem"])

        from delayu.models import SsoProvider

        SsoProvider.objects.update_or_create(
            subsystem=subsystem,
            name="Госуслуги (демо)",
            defaults={
                "provider_type": SsoProvider.ProviderType.ESIA,
                "client_id": "fuel-novorossiysk-demo",
                "is_active": True,
                "metadata": {
                    "demo": True,
                    "fuel_citizen": True,
                    "demo_name": "Петров Пётр Петрович",
                    "demo_phone": "79007654321",
                    "demo_sub": "esia-demo-nvr-001",
                },
            },
        )

        self.stdout.write(self.style.SUCCESS("Готово."))
        self.stdout.write("Жители:  http://127.0.0.1:8000/fuel/novorossiysk/")
        self.stdout.write(
            "АЗС:     http://127.0.0.1:8000/fuel/novorossiysk/azs/  "
            "(логин lukoildzerzh / PIN 1234)"
        )
        self.stdout.write("Штаб:    http://127.0.0.1:8000/fuel/  (логин fuel_nvr / fuel_nvr)")
        self.stdout.write("Продакшен: https://novorossiysk.<FUEL_PLATFORM_BASE_DOMAIN>/")

    def _citizen(self, subsystem, phone: str, full_name: str) -> FuelCitizen:
        citizen, _ = FuelCitizen.objects.update_or_create(
            subsystem=subsystem,
            phone=phone,
            defaults={"full_name": full_name},
        )
        return citizen

    def _seed_demo_applications(self, subsystem):
        from delayu.services.fuel import (
            approve_application,
            execute_redeem,
            next_application_number,
            reject_application,
        )

        subsystem.fuel_applications.all().delete()

        cats = {c.code: c for c in FuelCategory.objects.filter(subsystem=subsystem)}
        azs_by_code = {a.code: a for a in subsystem.fuel_azs_stations.all()}

        demo = [
            # pending (6)
            ("79001110001", "Иванов Иван Иванович", "II", "H456KT23", "ГАЗель Next", "7707083893", "МУП «Водоканал»", "pending", "lukoil-dzerzh-xvor", ""),
            ("79001110002", "Петрова Анна Сергеевна", "III", "M789OP152", "Hyundai Solaris", "", "", "pending", "rosneft-suhum-57", ""),
            ("79001110003", "Сидоров Алексей Петрович", "IV", "K321CX123", "Ford Transit", "2310031475", "ООО «Логистик Юг»", "pending", "gazprom-myskhak", ""),
            ("79001110004", "Козлова Мария Викторовна", "II", "B555MM93", "КАМАЗ 65115", "7702070139", "АО «Новоросморпорт»", "pending", "rosneft-lenina-2", ""),
            ("79001110005", "Новиков Дмитий Андреевич", "III", "T901AB77", "Skoda Octavia", "", "", "pending", "lukoil-suvorov-54", ""),
            ("79001110006", "Морозова Елена Игоревна", "IV", "E234HP23", "Volkswagen Crafter", "2312016641", "ИП Морозова Е.И.", "pending", "ufim-malozem", ""),
            # approved (8)
            ("79001110007", "Волков Сергей Николаевич", "I", "A111AA23", "УАЗ Патриот", "2315009263", "ГУП КК «Кубаньводкоммунэнерго»", "approved", "lukoil-dzerzh-211", ""),
            ("79001110008", "Соколова Ольга Павловна", "V", "P777PP23", "Lada Vesta", "", "", "approved", "rosneft-kunikova", ""),
            ("79001110009", "Лебедев Игорь Владимирович", "II", "C888CC93", "МАЗ 5337", "7707049388", "МУП «Новороссийсктеплоэнерго»", "approved", "gazprom-rail", ""),
            ("79001110010", "Кузнецов Павел Олегович", "III", "Y456YY152", "Kia Rio", "", "", "approved", "lukoil-lenina-7", ""),
            ("79001110011", "Фёдорова Наталья Юрьевна", "IV", "O123OO23", "Renault Master", "2311123456", "ООО «ТрансСервис»", "approved", "rosneft-zolryb", ""),
            ("79001110012", "Попов Артём Сергеевич", "V", "X999XX23", "Renault Logan", "", "", "approved", "tatneft-verhbak", ""),
            ("79001110013", "Васильева Татьяна Михайловна", "II", "H222HH23", "ПАЗ 32053", "2315987654", "МУП «Горэлектротранс»", "approved", "gazpromneft-gayduk", ""),
            ("79001110014", "Михайлов Роман Дмитриевич", "III", "K555KK77", "Toyota Camry", "", "", "approved", "lukoil-glebovka", ""),
            # rejected (4)
            ("79001110015", "Андреева Светлана Викторовна", "IV", "M333MM23", "Mercedes Sprinter", "0000000000", "ООО «Фиктив»", "rejected", "rosneft-suhum-64", "Недействительный ИНН организации"),
            ("79001110016", "Егоров Владислав Игоревич", "III", "B000BB00", "Hyundai Creta", "", "", "rejected", "lukoil-suhum-srz", "Некорректный госномер в базе ГИБДД"),
            ("79001110017", "Романова Ксения Алексеевна", "II", "T444TT23", "ЗИЛ 5301", "2310098765", "ООО «СтройЮг»", "rejected", "gazprom-natuh", "Превышен лимит заявок по категории"),
            ("79001110018", "Григорьев Максим Петрович", "IV", "A555AA55", "MAN TGL", "7743013902", "ООО «АвтоЛайн»", "rejected", "lukoil-raevskaya", "Документы не подтверждены"),
            # draft (2)
            ("79001110019", "Орлова Виктория Сергеевна", "V", "P111PP23", "Chery Tiggo", "", "", "draft", "rosneft-dzerzh-227", ""),
            ("79001110020", "Зайцев Никита Александрович", "III", "Y222YY23", "Geely Atlas", "", "", "draft", "lukoil-dzerzh-188", ""),
        ]

        created = 0
        for phone, name, cat_code, plate, make, inn, org, status, azs_code, reject_reason in demo:
            citizen = self._citizen(subsystem, phone, name)
            category = cats[cat_code]
            assigned = azs_by_code.get(azs_code)

            app = FuelApplication.objects.create(
                subsystem=subsystem,
                citizen=citizen,
                number=next_application_number(subsystem),
                category=category,
                plate=plate,
                vehicle_make=make,
                inn=inn,
                org_name=org,
                status=FuelApplication.Status.PENDING,
                assigned_azs=assigned,
            )
            created += 1

            if status == "approved":
                approve_application(app)
            elif status == "rejected":
                reject_application(app, reject_reason)
            elif status == "draft":
                app.status = FuelApplication.Status.DRAFT
                app.save(update_fields=["status"])

        # Несколько выдач топлива для дашборда
        permits = list(
            subsystem.fuel_permits.select_related("application", "assigned_azs").order_by("id")[:4]
        )
        for permit in permits:
            azs = permit.assigned_azs or subsystem.fuel_azs_stations.first()
            if azs and permit.remaining_liters > 20:
                try:
                    execute_redeem(permit, azs, Decimal("30"))
                except Exception:
                    pass

        self.stdout.write(
            f"Демо-заявки: {created} "
            f"(на проверке: {subsystem.fuel_applications.filter(status='pending').count()}, "
            f"одобрено: {subsystem.fuel_applications.filter(status='approved').count()}, "
            f"отклонено: {subsystem.fuel_applications.filter(status='rejected').count()}, "
            f"черновики: {subsystem.fuel_applications.filter(status='draft').count()})"
        )

    def _seed_demo_blacklist(self, subsystem):
        from delayu.services.fuel_analytics import add_blacklist_entry

        add_blacklist_entry(
            subsystem,
            plate="B000BB00",
            inn="",
            reason="Поддельный госномер (демо)",
        )
        add_blacklist_entry(
            subsystem,
            plate="",
            inn="0000000000",
            reason="Недействительный ИНН (демо)",
        )
        self.stdout.write(f"Чёрный список: {subsystem.fuel_blacklist.count()} записей")

    def _seed_parity_rule(self, subsystem):
        from delayu.models_fuel import FuelParityRule
        from delayu.services.fuel import get_or_create_parity_rule

        rule = get_or_create_parity_rule(subsystem)
        if not rule.message:
            rule.mode = FuelParityRule.Mode.CALENDAR
            rule.is_enabled = True
            rule.save(update_fields=["mode", "is_enabled", "updated_at"])
        self.stdout.write("Правило чётности ГРЗ настроено")

    def _seed_max_channel(self, subsystem):
        from delayu.models import MessengerChannel

        MessengerChannel.objects.update_or_create(
            subsystem=subsystem,
            code="max_fuel",
            defaults={
                "name": "MAX (топливный пропуск)",
                "channel_type": MessengerChannel.ChannelType.MAX,
                "webhook_url": "demo:max",
                "is_active": True,
                "notes": "Укажите URL API MAX для OTP и уведомлений о пропуске",
            },
        )
        self.stdout.write("Канал MAX для уведомлений настроен")
