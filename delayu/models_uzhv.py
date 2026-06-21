"""АИС УЖВ — предметная область (жилищный учёт, этап 1)."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class HousingCitizen(models.Model):
    """Заявитель / гражданин (ПДн)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_citizens"
    )
    last_name = models.CharField("Фамилия", max_length=128)
    first_name = models.CharField("Имя", max_length=128)
    middle_name = models.CharField("Отчество", max_length=128, blank=True)
    snils = models.CharField("СНИЛС", max_length=14, blank=True, db_index=True)
    passport_series = models.CharField("Серия паспорта", max_length=8, blank=True)
    passport_number = models.CharField("Номер паспорта", max_length=12, blank=True)
    passport_issued_at = models.DateField("Дата выдачи паспорта", null=True, blank=True)
    passport_issued_by = models.CharField("Кем выдан", max_length=255, blank=True)
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    email = models.EmailField("E-mail", blank=True)
    reg_address = models.CharField("Адрес регистрации", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Гражданин (УЖВ)"
        verbose_name_plural = "Гражданины (УЖВ)"
        ordering = ["last_name", "first_name"]

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(p for p in parts if p)


class HousingQueueCase(models.Model):
    """Учётное дело — нуждающийся в жилом помещении."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        REGISTERED = "registered", "На учёте"
        QUEUED = "queued", "В очереди"
        PROVIDED = "provided", "Обеспечен"
        REMOVED = "removed", "Снят с учёта"
        REJECTED = "rejected", "Отказ"

    class RemovalReason(models.TextChoices):
        PROVIDED = "provided", "Предоставлено жилое помещение"
        LOST_ELIGIBILITY = "lost_eligibility", "Утрата оснований"
        REFUSED = "refused", "Отказ заявителя"
        DUPLICATE = "duplicate", "Дублирование учёта"
        OTHER = "other", "Иное"

    class Category(models.TextChoices):
        GENERAL = "general", "Общая очередь"
        LOW_INCOME = "low_income", "Малоимущие"
        YOUNG_FAMILY = "young_family", "Молодые семьи"
        ORPHAN = "orphan", "Дети-сироты"
        VETERAN = "veteran", "Льготная категория"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_cases"
    )
    citizen = models.ForeignKey(
        HousingCitizen, on_delete=models.PROTECT, related_name="cases"
    )
    case_number = models.CharField("Номер дела", max_length=64, db_index=True)
    category = models.CharField(
        max_length=32, choices=Category.choices, default=Category.GENERAL
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    registered_at = models.DateField("Дата постановки на учёт", default=timezone.now)
    queue_position = models.PositiveIntegerField("Очерёдность", null=True, blank=True)
    income_verified = models.BooleanField("Доход проверен", default=False)
    low_income_conclusion = models.TextField("Заключение о малоимущности", blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_cases_assigned",
    )
    notes = models.TextField(blank=True)
    household_size = models.PositiveSmallIntegerField(
        "Число членов семьи", null=True, blank=True
    )
    monthly_income = models.DecimalField(
        "Среднемесячный доход, ₽",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    property_value = models.DecimalField(
        "Стоимость имущества, ₽",
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    per_capita_income = models.DecimalField(
        "Среднедушевой доход, ₽",
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )
    low_income_eligible = models.BooleanField("Признан малоимущим", null=True, blank=True)
    low_income_calculated_at = models.DateTimeField(null=True, blank=True)
    low_income_application_at = models.DateField(
        "Дата заявления (малоимущие)", null=True, blank=True
    )
    low_income_review_due_at = models.DateField(
        "Срок рассмотрения заявления", null=True, blank=True
    )
    removed_at = models.DateField("Дата снятия с учёта", null=True, blank=True)
    removal_reason = models.CharField(
        "Основание снятия с учёта",
        max_length=32,
        choices=RemovalReason.choices,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Учётное дело УЖВ"
        verbose_name_plural = "Учётные дела УЖВ"
        unique_together = [("subsystem", "case_number")]
        ordering = ["queue_position", "-registered_at"]

    def __str__(self):
        return f"{self.case_number} — {self.citizen.full_name}"


class HousingHouseholdMember(models.Model):
    """Член семьи заявителя (расчёт малоимущих)."""

    class Relation(models.TextChoices):
        APPLICANT = "applicant", "Заявитель"
        SPOUSE = "spouse", "Супруг(а)"
        CHILD = "child", "Ребёнок"
        DEPENDENT = "dependent", "Иждивенец"
        OTHER = "other", "Иное"

    case = models.ForeignKey(
        HousingQueueCase, on_delete=models.CASCADE, related_name="household_members"
    )
    full_name = models.CharField("ФИО", max_length=255)
    relation = models.CharField(
        max_length=16, choices=Relation.choices, default=Relation.OTHER
    )
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    snils = models.CharField("СНИЛС", max_length=14, blank=True)
    passport_series = models.CharField("Серия паспорта", max_length=8, blank=True)
    passport_number = models.CharField("Номер паспорта", max_length=12, blank=True)
    reg_address = models.CharField("Адрес регистрации", max_length=500, blank=True)
    monthly_income = models.DecimalField(
        "Месячный доход, ₽", max_digits=12, decimal_places=2, null=True, blank=True
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Член семьи"
        verbose_name_plural = "Состав семьи"
        ordering = ["sort_order", "pk"]

    def __str__(self):
        return self.full_name


class HousingCaseAttachment(models.Model):
    """Скан/вложение к учётному делу (малоимущие, сироты и др.)."""

    class DocKind(models.TextChoices):
        APPLICATION = "application", "Заявление"
        PASSPORT = "passport", "Паспорт / удостоверение"
        INCOME = "income", "Справка о доходах"
        PROPERTY = "property", "Сведения об имуществе"
        DECISION = "decision", "Решение / заключение"
        OTHER = "other", "Прочее"

    case = models.ForeignKey(
        HousingQueueCase, on_delete=models.CASCADE, related_name="attachments"
    )
    title = models.CharField("Наименование", max_length=255)
    doc_kind = models.CharField(
        max_length=16, choices=DocKind.choices, default=DocKind.OTHER
    )
    file = models.FileField("Файл", upload_to="uzhv/cases/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uzhv_attachments"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Вложение к делу УЖВ"
        verbose_name_plural = "Вложения к делам УЖВ"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class HousingCaseStatusHistory(models.Model):
    """История изменений статуса учётного дела (ТЗ п. 277)."""

    case = models.ForeignKey(
        HousingQueueCase, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        "Было", max_length=20, choices=HousingQueueCase.Status.choices, blank=True
    )
    to_status = models.CharField(
        "Стало", max_length=20, choices=HousingQueueCase.Status.choices
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uzhv_case_status_changes",
    )
    comment = models.TextField("Комментарий / основание", blank=True)

    class Meta:
        verbose_name = "История статуса дела"
        verbose_name_plural = "История статусов дел"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.case.case_number}: {self.from_status} → {self.to_status}"


class MunicipalBuilding(models.Model):
    """МКД / объект муниципального жилфонда."""

    class Condition(models.TextChoices):
        OK = "ok", "Исправный"
        EMERGENCY = "emergency", "Аварийный"
        RENOVATION = "renovation", "На расселении"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="municipal_buildings"
    )
    address = models.CharField("Адрес", max_length=500)
    cadastral_number = models.CharField("Кадастровый номер", max_length=64, blank=True)
    floors = models.PositiveSmallIntegerField("Этажность", null=True, blank=True)
    year_built = models.PositiveSmallIntegerField("Год постройки", null=True, blank=True)
    condition = models.CharField(
        max_length=20, choices=Condition.choices, default=Condition.OK
    )
    notes = models.TextField(blank=True)
    total_area_sqm = models.DecimalField(
        "Общая площадь, м²", max_digits=10, decimal_places=2, null=True, blank=True
    )
    residents_count = models.PositiveIntegerField("Численность жителей", null=True, blank=True)
    in_resettlement_program = models.BooleanField(
        "Программа расселения (4779)", default=False
    )
    in_reconstruction_zone = models.BooleanField(
        "В зоне реконструкции", default=False
    )
    reconstruction_program = models.CharField(
        "Программа / основание реконструкции", max_length=255, blank=True
    )
    reconstruction_since = models.DateField("В зоне с", null=True, blank=True)
    latitude = models.DecimalField(
        "Широта", max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        "Долгота", max_digits=9, decimal_places=6, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "МКД (жилфонд)"
        verbose_name_plural = "МКД (жилфонд)"
        ordering = ["address"]

    def __str__(self):
        return self.address

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


class MunicipalPremise(models.Model):
    """Жилое помещение в МКД."""

    class Status(models.TextChoices):
        FREE = "free", "Свободно"
        OCCUPIED = "occupied", "Занято"
        RESERVED = "reserved", "Резерв"

    building = models.ForeignKey(
        MunicipalBuilding, on_delete=models.CASCADE, related_name="premises"
    )
    number = models.CharField("Номер помещения", max_length=32)
    area_sqm = models.DecimalField(
        "Площадь, м²", max_digits=8, decimal_places=2, null=True, blank=True
    )
    rooms = models.PositiveSmallIntegerField("Комнат", null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.FREE
    )
    unfit_for_living = models.BooleanField("Непригодно для проживания", default=False)
    unfit_decision_ref = models.CharField(
        "№ акта / решения о непригодности", max_length=128, blank=True
    )
    unfit_decision_at = models.DateField("Дата признания непригодным", null=True, blank=True)
    unfit_reason = models.TextField("Основание непригодности", blank=True)
    usable_for_purpose = models.BooleanField(
        "Пригодно к использованию по назначению", default=True
    )
    specialized_orphan = models.BooleanField(
        "Специализированное (дети-сироты)", default=False
    )

    class Meta:
        verbose_name = "Жилое помещение"
        verbose_name_plural = "Жилые помещения"
        unique_together = [("building", "number")]
        ordering = ["building__address", "number"]

    def __str__(self):
        return f"{self.building.address}, кв. {self.number}"


class HousingPersonalAccount(models.Model):
    """Лицевой счёт по жилому помещению (ТЗ п. 4.6.3, 315)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_personal_accounts"
    )
    premise = models.OneToOneField(
        MunicipalPremise,
        on_delete=models.CASCADE,
        related_name="personal_account",
        verbose_name="Помещение",
    )
    account_number = models.CharField("№ лицевого счёта", max_length=64, db_index=True)
    tenant_citizen = models.ForeignKey(
        HousingCitizen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="personal_accounts",
        verbose_name="Наниматель / собственник",
    )
    living_area_sqm = models.DecimalField(
        "Жилая площадь, м²", max_digits=8, decimal_places=2, null=True, blank=True
    )
    total_area_sqm = models.DecimalField(
        "Общая площадь, м²", max_digits=8, decimal_places=2, null=True, blank=True
    )
    utility_services = models.TextField(
        "Коммунальные услуги",
        blank=True,
        help_text="Перечень услуг (отопление, ХВС, ГВС и т.п.)",
    )
    is_active = models.BooleanField("Открыт", default=True)
    opened_at = models.DateField("Дата открытия", default=timezone.now)
    closed_at = models.DateField("Дата закрытия", null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Лицевой счёт"
        verbose_name_plural = "Лицевые счета"
        unique_together = [("subsystem", "account_number")]
        ordering = ["account_number"]

    def __str__(self):
        return f"ЛС {self.account_number}"


class HousingPersonalAccountMember(models.Model):
    """Состав семьи по лицевому счёту."""

    class Relation(models.TextChoices):
        HEAD = "head", "Наниматель / собственник"
        SPOUSE = "spouse", "Супруг(а)"
        CHILD = "child", "Ребёнок"
        RELATIVE = "relative", "Родственник"
        OTHER = "other", "Иное"

    account = models.ForeignKey(
        HousingPersonalAccount, on_delete=models.CASCADE, related_name="members"
    )
    full_name = models.CharField("ФИО", max_length=255)
    relation = models.CharField(
        max_length=16, choices=Relation.choices, default=Relation.OTHER
    )
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    registered_from = models.DateField("Зарегистрирован с", default=timezone.now)
    registered_to = models.DateField("Снят с регистрации", null=True, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Член семьи (ЛС)"
        verbose_name_plural = "Состав семьи (ЛС)"
        ordering = ["sort_order", "full_name"]

    def __str__(self):
        return self.full_name


class HousingPersonalAccountHistory(models.Model):
    """История изменений лицевого счёта."""

    account = models.ForeignKey(
        HousingPersonalAccount, on_delete=models.CASCADE, related_name="history"
    )
    description = models.TextField("Событие")
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uzhv_account_history",
    )

    class Meta:
        verbose_name = "История лицевого счёта"
        verbose_name_plural = "История лицевых счетов"
        ordering = ["-changed_at"]

    def __str__(self):
        return self.description[:80]


class PrivateManagedPremise(models.Model):
    """Жилое помещение частного фонда с непосредственным управлением (ТЗ п. 314)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="private_managed_premises"
    )
    address = models.CharField("Адрес", max_length=500)
    premise_number = models.CharField("№ помещения", max_length=32, blank=True)
    cadastral_number = models.CharField("Кадастровый номер", max_length=64, blank=True)
    area_sqm = models.DecimalField(
        "Площадь, м²", max_digits=8, decimal_places=2, null=True, blank=True
    )
    rooms = models.PositiveSmallIntegerField("Комнат", null=True, blank=True)
    owner_name = models.CharField("Собственник", max_length=255)
    owner_phone = models.CharField("Телефон", max_length=32, blank=True)
    management_since = models.DateField("Управление с", null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Помещение частного фонда"
        verbose_name_plural = "Частный фонд (непосредственное управление)"
        ordering = ["address", "premise_number"]

    def __str__(self):
        num = f", кв. {self.premise_number}" if self.premise_number else ""
        return f"{self.address}{num}"


class HousingContract(models.Model):
    """Договор найма / соцнайма (упрощённый реестр)."""

    class ContractType(models.TextChoices):
        SOCIAL = "social", "Социальный найм"
        SPECIAL = "special", "Специализированный"
        COMMERCIAL = "commercial", "Коммерческий"
        PRIVATIZATION = "privatization", "Приватизация"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_contracts"
    )
    contract_number = models.CharField("Номер", max_length=64)
    contract_type = models.CharField(max_length=20, choices=ContractType.choices)
    citizen = models.ForeignKey(
        HousingCitizen, on_delete=models.PROTECT, related_name="contracts"
    )
    premise = models.ForeignKey(
        MunicipalPremise,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="contracts",
    )
    signed_at = models.DateField("Дата заключения", default=timezone.now)
    valid_until = models.DateField("Действует до", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    terminated_at = models.DateField("Дата расторжения", null=True, blank=True)
    termination_reason = models.CharField("Основание расторжения", max_length=500, blank=True)
    notes = models.TextField("Примечание", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Договор УЖВ"
        verbose_name_plural = "Договоры УЖВ"
        unique_together = [("subsystem", "contract_number")]
        ordering = ["-signed_at"]


class HousingContractConsent(models.Model):
    """Согласия и регистрация действий по договору (ТЗ п. 297–305)."""

    class ConsentType(models.TextChoices):
        SUBLET = "sublet", "Поднайм"
        MOVE_IN = "move_in", "Вселение членов семьи"
        EXCHANGE = "exchange", "Обмен жилого помещения"
        TEMP_BAN = "temp_ban", "Запрет временных жильцов"
        TERMINATION_OBLIGATION = "termination_ob", "Обязательство о расторжении"
        EMERGENCY_AGREEMENT = "emergency", "Соглашение об изъятии (аварийный)"
        PRIVATIZATION = "privatization", "Передача в собственность"
        PRIVATE_TO_MUNICIPAL = "private_to_muni", "Безвозмездная передача в муниципальную"

    class Decision(models.TextChoices):
        PENDING = "pending", "На оформлении"
        APPROVED = "approved", "Согласие"
        DENIED = "denied", "Отказ"
        REGISTERED = "registered", "Зарегистрировано"

    contract = models.ForeignKey(
        HousingContract, on_delete=models.CASCADE, related_name="consents"
    )
    consent_type = models.CharField(
        max_length=20, choices=ConsentType.choices, verbose_name="Вид"
    )
    decision = models.CharField(
        max_length=16,
        choices=Decision.choices,
        default=Decision.PENDING,
        verbose_name="Решение",
    )
    subject = models.CharField(
        "Содержание (кого вселяют, с кем обмен и т.п.)",
        max_length=500,
        blank=True,
    )
    document_number = models.CharField("№ документа", max_length=64, blank=True)
    registered_at = models.DateField("Дата регистрации", default=timezone.now)
    notes = models.TextField("Примечание", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uzhv_contract_consents",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Согласие / действие по договору"
        verbose_name_plural = "Согласия и действия по договорам"
        ordering = ["-registered_at", "-created_at"]

    def __str__(self):
        return f"{self.contract.contract_number} — {self.get_consent_type_display()}"


class HousingContractAttachment(models.Model):
    """Скан-копия документа по договору (ТЗ п. 305)."""

    class DocKind(models.TextChoices):
        CONTRACT = "contract", "Договор"
        CONSENT = "consent", "Согласие / отказ"
        AGREEMENT = "agreement", "Соглашение"
        OTHER = "other", "Прочее"

    contract = models.ForeignKey(
        HousingContract, on_delete=models.CASCADE, related_name="attachments"
    )
    title = models.CharField("Наименование", max_length=255)
    doc_kind = models.CharField(
        max_length=16, choices=DocKind.choices, default=DocKind.OTHER
    )
    file = models.FileField("Файл", upload_to="uzhv/contracts/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uzhv_contract_files"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Вложение к договору"
        verbose_name_plural = "Вложения к договорам"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class HousingAppeal(models.Model):
    """Обращение гражданина (контроль срока ответа 30 календарных дней)."""

    class Status(models.TextChoices):
        REGISTERED = "registered", "Зарегистрировано"
        IN_WORK = "in_work", "В работе"
        ANSWERED = "answered", "Ответ дан"
        CLOSED = "closed", "Закрыто"

    class ConclusionKind(models.TextChoices):
        INFO = "info", "Информационный ответ"
        REFUSAL = "refusal", "Отказ"
        REDIRECT = "redirect", "Направление в другой орган"
        HOUSING = "housing", "Заключение по жилищному вопросу"
        OTHER = "other", "Прочее"

    SLA_DAYS = 30

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_appeals"
    )
    appeal_number = models.CharField("Номер обращения", max_length=64, db_index=True)
    received_at = models.DateField("Дата поступления", default=timezone.now)
    due_date = models.DateField("Срок ответа")
    citizen = models.ForeignKey(
        HousingCitizen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appeals",
    )
    housing_case = models.ForeignKey(
        HousingQueueCase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="appeals",
        verbose_name="Учётное дело",
    )
    correspondence = models.OneToOneField(
        "Correspondence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_appeal",
    )
    subject = models.CharField("Тема", max_length=500)
    body = models.TextField("Содержание", blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.REGISTERED
    )
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_appeals_assigned",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="housing_appeals_created",
    )
    answer_text = models.TextField("Текст ответа", blank=True)
    answered_at = models.DateField("Дата ответа", null=True, blank=True)
    conclusion_kind = models.CharField(
        "Вид заключения",
        max_length=16,
        choices=ConclusionKind.choices,
        blank=True,
    )
    outgoing_correspondence = models.OneToOneField(
        "Correspondence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_appeal_outgoing",
        verbose_name="Исходящий ответ (M24)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Обращение гражданина"
        verbose_name_plural = "Обращения граждан"
        unique_together = [("subsystem", "appeal_number")]
        ordering = ["-received_at", "-appeal_number"]

    def __str__(self):
        return f"{self.appeal_number} — {self.subject[:60]}"

    @property
    def is_overdue(self) -> bool:
        if self.status in (self.Status.ANSWERED, self.Status.CLOSED):
            return False
        return self.due_date < timezone.now().date()

    @property
    def days_left(self) -> int:
        return (self.due_date - timezone.now().date()).days


class HousingAppealStatusHistory(models.Model):
    """История статусов обращения (ТЗ п. 348–354)."""

    appeal = models.ForeignKey(
        HousingAppeal, on_delete=models.CASCADE, related_name="status_history"
    )
    from_status = models.CharField(
        "Было", max_length=20, choices=HousingAppeal.Status.choices, blank=True
    )
    to_status = models.CharField(
        "Стало", max_length=20, choices=HousingAppeal.Status.choices
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="uzhv_appeal_status_changes",
    )
    comment = models.TextField("Комментарий", blank=True)

    class Meta:
        verbose_name = "История статуса обращения"
        verbose_name_plural = "История статусов обращений"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.appeal.appeal_number}: {self.from_status} → {self.to_status}"


class HousingAppealAttachment(models.Model):
    """Вложение к обращению гражданина."""

    class DocKind(models.TextChoices):
        INCOMING = "incoming", "Входящее обращение"
        EVIDENCE = "evidence", "Подтверждающие документы"
        OUTGOING = "outgoing", "Исходящий ответ"
        OTHER = "other", "Прочее"

    appeal = models.ForeignKey(
        HousingAppeal, on_delete=models.CASCADE, related_name="attachments"
    )
    title = models.CharField("Наименование", max_length=255)
    doc_kind = models.CharField(
        max_length=16, choices=DocKind.choices, default=DocKind.OTHER
    )
    file = models.FileField("Файл", upload_to="uzhv/appeals/%Y/%m/")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uzhv_appeal_attachments"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Вложение к обращению"
        verbose_name_plural = "Вложения к обращениям"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title


class YoungFamilyRecord(models.Model):
    """Подсистема «Молодые семьи» (ТЗ п. 279–284)."""

    class Program(models.TextChoices):
        JSK = "jsk", "Члены ЖСК (2704-КЗ)"
        ECONOMY = "economy", "Жильё экономкласса"

    case = models.OneToOneField(
        HousingQueueCase, on_delete=models.CASCADE, related_name="young_family"
    )
    spouse_last_name = models.CharField("Фамилия супруга(и)", max_length=128, blank=True)
    spouse_first_name = models.CharField("Имя супруга(и)", max_length=128, blank=True)
    spouse_middle_name = models.CharField("Отчество супруга(и)", max_length=128, blank=True)
    marriage_date = models.DateField("Дата брака", null=True, blank=True)
    spouse_birth_date = models.DateField("Дата рождения супруга(и)", null=True, blank=True)
    children_count = models.PositiveSmallIntegerField("Детей", default=0)
    program = models.CharField(
        max_length=16, choices=Program.choices, default=Program.JSK
    )
    meets_criteria = models.BooleanField("Соответствует критериям", default=False)
    criteria_notes = models.TextField("Заключение по критериям", blank=True)
    criteria_checked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Молодая семья"
        verbose_name_plural = "Молодые семьи"

    @property
    def spouse_full_name(self):
        parts = [self.spouse_last_name, self.spouse_first_name, self.spouse_middle_name]
        return " ".join(p for p in parts if p) or "—"


class OrphanHousingRecord(models.Model):
    """Подсистема «Дети-сироты» (ТЗ п. 285–291)."""

    class HousingStatus(models.TextChoices):
        LIST_PENDING = "list_pending", "Ожидает включения в список"
        IN_LIST = "in_list", "В списке Минтруда"
        HOUSING = "housing", "Предоставлено жильё"
        PAYMENT = "payment", "Выплата"
        CONTRACT_SHORT = "contract_short", "Сокращение срока найма"

    case = models.OneToOneField(
        HousingQueueCase, on_delete=models.CASCADE, related_name="orphan_record"
    )
    mintrud_decision_number = models.CharField("№ решения Минтруда КК", max_length=64, blank=True)
    mintrud_decision_date = models.DateField(null=True, blank=True)
    housing_status = models.CharField(
        max_length=20, choices=HousingStatus.choices, default=HousingStatus.LIST_PENDING
    )
    assigned_premise = models.ForeignKey(
        "MunicipalPremise",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="orphan_assignments",
        verbose_name="Закреплённое спец. помещение",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Дело дети-сироты"
        verbose_name_plural = "Дети-сироты"


class HousingInspectionPlan(models.Model):
    """План внеплановых проверок (ТЗ п. 321)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        APPROVED = "approved", "Утверждён"
        IN_PROGRESS = "in_progress", "Исполняется"
        COMPLETED = "completed", "Выполнен"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_inspection_plans"
    )
    plan_number = models.CharField("№ плана", max_length=64, db_index=True)
    title = models.CharField("Наименование", max_length=255)
    period_from = models.DateField("Период с")
    period_to = models.DateField("Период по")
    basis = models.TextField("Основание внеплановых проверок", blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    approved_at = models.DateField("Дата утверждения", null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="uzhv_inspection_plans",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "План проверок"
        verbose_name_plural = "Планы внеплановых проверок"
        unique_together = [("subsystem", "plan_number")]
        ordering = ["-period_from", "-plan_number"]

    def __str__(self):
        return f"{self.plan_number} — {self.title}"


class HousingInspection(models.Model):
    """Проверка муниципального жилищного контроля (ТЗ п. 318–330)."""

    class InspectionType(models.TextChoices):
        PLANNED = "planned", "Плановая"
        UNPLANNED = "unplanned", "Внеплановая"

    class ObjectType(models.TextChoices):
        MKD = "mkd", "МКД"
        UK = "uk", "УК"
        TSJ = "tsj", "ТСЖ"
        JSK = "jsk", "ЖСК"
        CITIZEN = "citizen", "Гражданин"

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирована"
        IN_PROGRESS = "in_progress", "Проводится"
        COMPLETED = "completed", "Завершена"
        CANCELLED = "cancelled", "Отменена"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_inspections"
    )
    plan = models.ForeignKey(
        HousingInspectionPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
        verbose_name="План внеплановых проверок",
    )
    inspection_number = models.CharField("№ проверки", max_length=64, db_index=True)
    inspection_type = models.CharField(
        max_length=16, choices=InspectionType.choices, default=InspectionType.PLANNED
    )
    object_type = models.CharField(
        max_length=16, choices=ObjectType.choices, default=ObjectType.MKD
    )
    building = models.ForeignKey(
        MunicipalBuilding,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspections",
    )
    counterparty_name = models.CharField("Объект (УК/ТСЖ/ФИО)", max_length=255, blank=True)
    check_subject = models.CharField("Предмет проверки", max_length=255, blank=True)
    planned_date = models.DateField("Дата проверки", default=timezone.now)
    completed_date = models.DateField(null=True, blank=True)
    inspector = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_inspections",
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PLANNED
    )
    result_summary = models.TextField("Результаты / акт", blank=True)
    violations_found = models.BooleanField("Выявлены нарушения", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Проверка (жилконтроль)"
        verbose_name_plural = "Проверки (жилконтроль)"
        unique_together = [("subsystem", "inspection_number")]
        ordering = ["-planned_date", "-inspection_number"]

    def __str__(self):
        return f"{self.inspection_number} — {self.get_object_type_display()}"


class HousingInspectionOrder(models.Model):
    """Предписание на проведение проверки (ТЗ п. 322)."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Выдано"
        SCHEDULED = "scheduled", "Проверка назначена"
        COMPLETED = "completed", "Проверка проведена"
        CANCELLED = "cancelled", "Отменено"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_inspection_orders"
    )
    order_number = models.CharField("№ предписания", max_length=64, db_index=True)
    addressee = models.CharField("Адресат (УК, ТСЖ, ФИО)", max_length=255)
    object_type = models.CharField(
        max_length=16,
        choices=HousingInspection.ObjectType.choices,
        default=HousingInspection.ObjectType.MKD,
    )
    building = models.ForeignKey(
        MunicipalBuilding,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspection_orders",
    )
    check_address = models.CharField("Адрес объекта", max_length=500, blank=True)
    check_subject = models.CharField("Предмет проверки", max_length=255, blank=True)
    plan = models.ForeignKey(
        HousingInspectionPlan,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="inspection_orders",
        verbose_name="План проверок",
    )
    inspection = models.OneToOneField(
        HousingInspection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conduct_order",
        verbose_name="Зарегистрированная проверка",
    )
    issued_at = models.DateField("Дата выдачи", default=timezone.now)
    conduct_by = models.DateField("Срок проведения проверки")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ISSUED
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Предписание на проведение проверки"
        verbose_name_plural = "Предписания на проведение проверок"
        unique_together = [("subsystem", "order_number")]
        ordering = ["-issued_at", "-order_number"]

    @property
    def is_overdue(self) -> bool:
        if self.status in (self.Status.COMPLETED, self.Status.CANCELLED):
            return False
        return self.conduct_by < timezone.now().date()

    def __str__(self):
        return f"{self.order_number} — {self.addressee[:40]}"


class HousingPrescription(models.Model):
    """Предписание об устранении нарушений."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Выдано"
        IN_PROGRESS = "in_progress", "Исполняется"
        FULFILLED = "fulfilled", "Исполнено"
        OVERDUE = "overdue", "Просрочено"
        CANCELLED = "cancelled", "Отменено"

    inspection = models.ForeignKey(
        HousingInspection, on_delete=models.CASCADE, related_name="prescriptions"
    )
    prescription_number = models.CharField("№ предписания", max_length=64)
    issued_at = models.DateField("Дата выдачи", default=timezone.now)
    due_date = models.DateField("Срок устранения")
    description = models.TextField("Содержание")
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ISSUED
    )
    fulfilled_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Предписание об устранении"
        verbose_name_plural = "Предписания об устранении"
        ordering = ["due_date"]

    @property
    def is_overdue(self) -> bool:
        if self.status in (self.Status.FULFILLED, self.Status.CANCELLED):
            return False
        return self.due_date < timezone.now().date()


class HousingCourtCase(models.Model):
    """Судебное дело по жилищному контролю (ТЗ п. 328–329, ОТЧ-10)."""

    class Status(models.TextChoices):
        OPEN = "open", "В производстве"
        HEARING = "hearing", "Назначено заседание"
        DECISION = "decision", "Решение вынесено"
        ENFORCEMENT = "enforcement", "Исполнительное производство"
        CLOSED = "closed", "Завершено"
        CANCELLED = "cancelled", "Прекращено"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_court_cases"
    )
    inspection = models.ForeignKey(
        HousingInspection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="court_cases",
    )
    prescription = models.ForeignKey(
        HousingPrescription,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="court_cases",
    )
    court_name = models.CharField("Наименование суда", max_length=255)
    case_number = models.CharField("№ дела", max_length=64, db_index=True)
    check_address = models.CharField("Адрес проверки", max_length=500, blank=True)
    defendant_name = models.CharField("Ответчик (ФИО/организация)", max_length=255, blank=True)
    next_hearing_date = models.DateField("Дата заседания", null=True, blank=True)
    ufssp_reference = models.CharField("№ ИП (УФССП)", max_length=128, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.OPEN
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Судебное дело (УЖВ)"
        verbose_name_plural = "Судебные дела (УЖВ)"
        unique_together = [("subsystem", "case_number")]
        ordering = ["-next_hearing_date", "-case_number"]

    def __str__(self):
        return f"{self.case_number} — {self.court_name}"


class HousingEnforcementProceeding(models.Model):
    """Исполнительное производство УФССП (ТЗ п. 330)."""

    class Status(models.TextChoices):
        OPEN = "open", "Возбуждено"
        IN_PROGRESS = "in_progress", "Исполняется"
        SUSPENDED = "suspended", "Приостановлено"
        COMPLETED = "completed", "Окончено"
        RETURNED = "returned", "Возвращено в суд"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_enforcement_proceedings"
    )
    court_case = models.ForeignKey(
        HousingCourtCase,
        on_delete=models.CASCADE,
        related_name="enforcement_proceedings",
        verbose_name="Судебное дело",
    )
    proceeding_number = models.CharField("№ исполнительного производства", max_length=128, db_index=True)
    debtor_name = models.CharField("Должник", max_length=255)
    check_address = models.CharField("Адрес проверки", max_length=500, blank=True)
    court_decision = models.TextField("Решение суда", blank=True)
    initiated_at = models.DateField("Дата возбуждения", default=timezone.now)
    completed_at = models.DateField("Дата окончания", null=True, blank=True)
    bailiff_office = models.CharField("Подразделение УФССП", max_length=255, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.OPEN
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Исполнительное производство"
        verbose_name_plural = "Исполнительные производства"
        unique_together = [("subsystem", "proceeding_number")]
        ordering = ["-initiated_at", "-proceeding_number"]

    def __str__(self):
        return f"ИП {self.proceeding_number}"


class HousingInteragencyRequest(models.Model):
    """Межведомственный запрос (ручной учёт без СМЭВ, ТЗ ОТЧ-8)."""

    class RequestType(models.TextChoices):
        ROSREESTR = "rosreestr", "Росреестр / ЕГРН"
        MVD = "mvd", "МВД"
        ZAGS = "zags", "ЗАГС"
        FNS = "fns", "ФНС"
        BTI = "bti", "БТИ"
        MINTRUD = "mintrud", "Минтруд КК"
        SOCIAL = "social", "Соцзащита / Катарсис"
        OTHER = "other", "Иное ведомство"

    class Channel(models.TextChoices):
        MANUAL = "manual", "Ручной (без интеграции)"
        SMEV = "smev", "СМЭВ (не активен)"
        FILE = "file", "Обмен файлом"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SENT = "sent", "Отправлен"
        AWAITING = "awaiting", "Ожидает ответа"
        ANSWERED = "answered", "Ответ получен"
        OVERDUE = "overdue", "Просрочен"
        CANCELLED = "cancelled", "Отменён"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="housing_interagency_requests"
    )
    request_number = models.CharField("№ запроса", max_length=64, db_index=True)
    request_type = models.CharField(
        max_length=20, choices=RequestType.choices, default=RequestType.OTHER
    )
    channel = models.CharField(
        max_length=16, choices=Channel.choices, default=Channel.MANUAL
    )
    recipient_name = models.CharField("Адресат", max_length=255)
    subject = models.CharField("Тема / основание", max_length=500)
    housing_case = models.ForeignKey(
        HousingQueueCase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interagency_requests",
    )
    citizen = models.ForeignKey(
        HousingCitizen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="interagency_requests",
    )
    sent_at = models.DateField("Дата отправки", default=timezone.now)
    due_date = models.DateField("Срок ответа")
    answered_at = models.DateField(null=True, blank=True)
    response_summary = models.TextField("Содержание ответа", blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.SENT
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="housing_interagency_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Межведомственный запрос"
        verbose_name_plural = "Межведомственные запросы"
        unique_together = [("subsystem", "request_number")]
        ordering = ["-sent_at", "-request_number"]

    @property
    def is_overdue(self) -> bool:
        if self.status in (self.Status.ANSWERED, self.Status.CANCELLED):
            return False
        return self.due_date < timezone.now().date()

    @property
    def responsible_user(self):
        if self.housing_case_id and self.housing_case.assignee_id:
            return self.housing_case.assignee
        return self.created_by

    @property
    def responsible_label(self) -> str:
        user = self.responsible_user
        if not user:
            return "—"
        return user.get_full_name() or user.username

    def __str__(self):
        return f"{self.request_number} — {self.recipient_name}"


class HousingAdminProtocol(models.Model):
    """Протокол об административном правонарушении (Закон КК № 608-КЗ)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Проект"
        ISSUED = "issued", "Составлен"
        PAID = "paid", "Штраф оплачен"
        APPEAL = "appeal", "Обжалование"
        CANCELLED = "cancelled", "Отменён"

    inspection = models.ForeignKey(
        HousingInspection, on_delete=models.CASCADE, related_name="admin_protocols"
    )
    protocol_number = models.CharField("№ протокола", max_length=64)
    protocol_date = models.DateField("Дата составления", default=timezone.now)
    legal_article = models.CharField("Статья Закона КК / КоАП", max_length=128)
    violator_name = models.CharField("Привлекаемое лицо", max_length=255)
    fine_amount = models.DecimalField(
        "Сумма штрафа, ₽", max_digits=12, decimal_places=2, null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ISSUED
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Протокол об АП"
        verbose_name_plural = "Протоколы об АП"
        ordering = ["-protocol_date", "-protocol_number"]

    def __str__(self):
        return f"{self.protocol_number} — {self.violator_name}"
