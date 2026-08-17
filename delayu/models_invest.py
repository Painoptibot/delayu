"""Инвестконтур Кубани — доменные модели (тенант = Subsystem)."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class InvestInvestor(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_investors")
    name = models.CharField("Наименование", max_length=255)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    extras = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["subsystem", "inn"]),
        ]

    def __str__(self):
        return self.name


class InvestProject(models.Model):
    class Funnel(models.TextChoices):
        ATTRACTION = "attraction", "Привлечение"
        SUPPORT = "support", "Сопровождение"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_projects")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="invest_projects",
        verbose_name="МО / территория",
    )
    code = models.CharField("Код", max_length=64)
    name = models.CharField("Наименование", max_length=255)
    investor_name = models.CharField("Инвестор", max_length=255, blank=True)
    investor_entity = models.ForeignKey(
        InvestInvestor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
        verbose_name="Юрлицо инвестора",
    )
    industry = models.CharField("Отрасль", max_length=128, blank=True)
    description = models.TextField("Описание проекта", blank=True)
    funnel = models.CharField(max_length=16, choices=Funnel.choices, default=Funnel.ATTRACTION)
    stage = models.CharField("Стадия", max_length=32, default="lead")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="invest_projects_owned",
    )
    contact_person = models.CharField("Контактное лицо", max_length=255, blank=True)
    contact_phone = models.CharField("Телефон", max_length=64, blank=True)
    contact_email = models.EmailField("E-mail", blank=True)
    investment_amount = models.DecimalField(
        "Объём инвестиций, млн руб.", max_digits=18, decimal_places=2, null=True, blank=True
    )
    jobs_count = models.PositiveIntegerField("Рабочие места", null=True, blank=True)
    support_measures = models.TextField("Меры поддержки", blank=True)
    planned_start = models.DateField("План старта", null=True, blank=True)
    planned_end = models.DateField("План ввода", null=True, blank=True)
    municipality_notes = models.TextField("Комментарий МО", blank=True)
    external_ids = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class InvestSite(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        IN_REVIEW = "in_review", "На проверке"
        ACTUAL = "actual", "Актуальный"
        ARCHIVED = "archived", "Архив"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_sites")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="invest_sites",
    )
    cadastral_number = models.CharField("Кадастровый номер", max_length=64)
    name = models.CharField("Наименование", max_length=255)
    address = models.TextField("Адрес / местоположение", blank=True)
    area_ha = models.DecimalField("Площадь, га", max_digits=12, decimal_places=4, null=True, blank=True)
    land_category = models.CharField("Категория земель", max_length=128, blank=True)
    vri = models.CharField("ВРИ", max_length=255, blank=True)
    right_type = models.CharField("Вид права", max_length=128, blank=True)
    encumbrances = models.TextField("Обременения / ограничения", blank=True)
    zone_info = models.TextField("Зоны / пересечения (черновик)", blank=True)
    restriction_zones = models.JSONField("Ограничительные зоны", default=list, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    completeness_pct = models.PositiveSmallIntegerField("Полнота карточки, %", default=0)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    egrn_updated_at = models.DateTimeField("Данные ЕГРН обновлены", null=True, blank=True)
    last_smev_at = models.DateTimeField("Последний запрос СМЭВ", null=True, blank=True)
    external_ids = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "cadastral_number")]
        ordering = ["cadastral_number"]

    def __str__(self):
        return self.cadastral_number


class InvestProjectSite(models.Model):
    class Role(models.TextChoices):
        CANDIDATE = "candidate", "Кандидат"
        PROPOSED = "proposed", "Предложен"
        BOOKED = "booked", "Забронирован"
        SELECTED = "selected", "Выбран"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="site_links")
    site = models.ForeignKey(InvestSite, on_delete=models.CASCADE, related_name="project_links")
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CANDIDATE)
    booked_until = models.DateTimeField("Бронь до", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("project", "site")]


class InvestHandoff(models.Model):
    class Status(models.TextChoices):
        REQUESTED = "requested", "Запрошена"
        ACCEPTED = "accepted", "Принята"
        RETURNED = "returned", "Возвращена"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="handoffs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.REQUESTED)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class InvestPackage(models.Model):
    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="packages")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class InvestPackageSnapshot(models.Model):
    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="package_snapshots")
    package = models.ForeignKey(InvestPackage, on_delete=models.CASCADE, related_name="snapshots")
    handoff = models.ForeignKey(
        InvestHandoff, null=True, blank=True, on_delete=models.SET_NULL, related_name="package_snapshots"
    )
    decision = models.CharField(max_length=16)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class InvestPackageItem(models.Model):
    class Status(models.TextChoices):
        MISSING = "missing", "Нет"
        PENDING = "pending", "Ожидание"
        ATTACHED = "attached", "Приложено"
        OVERDUE = "overdue", "Просрочено"

    package = models.ForeignKey(InvestPackage, on_delete=models.CASCADE, related_name="items")
    code = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    required = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.MISSING)
    file = models.FileField(upload_to="invest/packages/", blank=True)
    document = models.ForeignKey(
        "DocumentFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invest_package_items",
    )
    due_at = models.DateTimeField(null=True, blank=True)


class InvestRoadmapItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Открыт"
        OVERDUE = "overdue", "Просрочено"
        DONE = "done", "Выполнено"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="roadmap_items")
    code = models.CharField(max_length=64)
    title = models.CharField(max_length=255)
    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("project", "code")]
        ordering = ["due_at", "code"]

    def __str__(self):
        return f"{self.project.code} — {self.title}"


class InvestSupportTrackItem(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Открыта"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Завершена"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="support_track_items")
    title = models.CharField("Мера поддержки", max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    due_at = models.DateField("Срок", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "created_at"]

    def __str__(self):
        return self.title


class InvestProtocol(models.Model):
    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="protocols")
    title = models.CharField("Протокол намерений", max_length=255)
    signed_at = models.DateField("Дата подписания", null=True, blank=True)
    document = models.ForeignKey(
        "DocumentFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invest_protocols",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-signed_at", "-created_at"]

    def __str__(self):
        return self.title


class InvestOivApproval(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        APPROVED = "approved", "Согласовано"
        REJECTED = "rejected", "Отказ"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="oiv_approvals")
    agency_name = models.CharField("ОИВ", max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    due_at = models.DateField("Срок", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["due_at", "agency_name"]

    def __str__(self):
        return self.agency_name


class InvestStopFactor(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Открыт"
        BLOCKING = "blocking", "Блокирует"
        RESOLVED = "resolved", "Снят"

    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="stop_factors")
    title = models.CharField("Стоп-фактор", max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["status", "created_at"]

    def __str__(self):
        return self.title


class InvestImportBatch(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        REVIEWING = "reviewing", "На проверке"
        DONE = "done", "Завершён"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_import_batches")
    organization = models.ForeignKey(
        "Organization", on_delete=models.PROTECT, related_name="invest_import_batches",
    )
    source_file = models.FileField(upload_to="invest/imports/", blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Import {self.pk} — {self.organization.code}"


class InvestImportRow(models.Model):
    class Action(models.TextChoices):
        NEW_PROJECT = "new_project", "Новый проект"
        CHANGED_PROJECT = "changed_project", "Изменён проект"
        GAP = "gap", "Нет в файле"
        NEW_SITE = "new_site", "Новая площадка"
        CHANGED_SITE = "changed_site", "Изменена площадка"

    class Resolution(models.TextChoices):
        PENDING = "pending", "Ожидает"
        APPLIED = "applied", "Применено"
        SKIPPED = "skipped", "Пропущено"

    batch = models.ForeignKey(InvestImportBatch, on_delete=models.CASCADE, related_name="rows")
    row_number = models.PositiveIntegerField(default=0)
    action = models.CharField(max_length=32, choices=Action.choices)
    resolution = models.CharField(max_length=16, choices=Resolution.choices, default=Resolution.PENDING)
    payload = models.JSONField(default=dict, blank=True)
    target_project = models.ForeignKey(
        InvestProject, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_rows",
    )
    target_site = models.ForeignKey(
        InvestSite, null=True, blank=True, on_delete=models.SET_NULL, related_name="import_rows",
    )
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["row_number"]

    def __str__(self):
        return f"{self.batch_id}#{self.row_number} {self.action}"


class InvestSmevRequest(models.Model):
    """Тестовый журнал запросов СМЭВ (mock, без промышленного шлюза)."""

    class Service(models.TextChoices):
        EGRN = "egrn", "ЕГРН (кадастр / права)"
        ISOGD = "isogd", "ИСОГД / ФГИС ТП"
        RGIS = "rgis", "РГИС (пересечения)"

    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        LIVE_PENDING = "live_pending", "Ожидает live-ответ"
        DONE = "done", "Получен ответ"
        ERROR = "error", "Ошибка"
        APPLIED = "applied", "Применено к карточке"
        DEAD_LETTER = "dead_letter", "Dead-letter"
        TIMEOUT = "timeout", "Таймаут"
        SCHEMA_ERROR = "schema_error", "Ошибка схемы"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_smev_requests")
    site = models.ForeignKey(InvestSite, on_delete=models.CASCADE, related_name="smev_requests")
    service = models.CharField(max_length=16, choices=Service.choices, default=Service.EGRN)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    is_mock = models.BooleanField("Тестовый контур", default=True)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    message_id = models.CharField(max_length=64, blank=True, db_index=True)
    retries = models.PositiveSmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=3)
    timeout_at = models.DateTimeField(null=True, blank=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True)
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    audit_trail = models.JSONField(default=list, blank=True)
    error_message = models.CharField(max_length=512, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запрос СМЭВ (инвест)"
        verbose_name_plural = "Запросы СМЭВ (инвест)"

    def __str__(self):
        return f"{self.get_service_display()} · {self.site.cadastral_number}"

    @property
    def mode_label(self) -> str:
        return "Sandbox" if self.is_mock else "Live"

    def append_audit(self, action: str, *, actor=None, details: dict | None = None, save: bool = True) -> None:
        trail = list(self.audit_trail or [])
        trail.append(
            {
                "action": action,
                "actor": getattr(actor, "username", "") if actor else "",
                "details": details or {},
                "created_at": timezone.now().isoformat(),
            }
        )
        self.audit_trail = trail
        if save:
            self.save(update_fields=["audit_trail"])

    def retry_or_dead_letter(self, *, actor=None, reason: str = ""):
        self.retries += 1
        update_fields = ["retries", "audit_trail"]
        if self.retries >= self.max_retries:
            self.status = self.Status.DEAD_LETTER
            self.dead_lettered_at = timezone.now()
            update_fields += ["status", "dead_lettered_at"]
            action = "dead_letter"
        else:
            self.status = self.Status.QUEUED
            update_fields.append("status")
            action = "retry"
        self.append_audit(action, actor=actor, details={"reason": reason, "retries": self.retries}, save=False)
        self.save(update_fields=update_fields)
        return self

    def timeout_to_dead_letter(self, *, actor=None, reason: str = "timeout"):
        now = timezone.now()
        self.status = self.Status.DEAD_LETTER
        self.dead_lettered_at = now
        if self.timeout_at is None:
            self.timeout_at = now
        self.append_audit("timeout", actor=actor, details={"reason": reason}, save=False)
        self.append_audit("dead_letter", actor=actor, details={"reason": reason}, save=False)
        self.save(update_fields=["status", "timeout_at", "dead_lettered_at", "audit_trail"])
        return self


class InvestSmevInfoType(models.Model):
    """НСИ видов сведений СМЭВ для demo-validation contracts."""

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    service = models.CharField(max_length=16, choices=InvestSmevRequest.Service.choices)
    contract_version = models.CharField(max_length=64, blank=True)
    schema_json = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["service", "code"]
        verbose_name = "Вид сведений СМЭВ"
        verbose_name_plural = "Виды сведений СМЭВ"

    def __str__(self):
        return f"{self.service}:{self.code}"


class InvestAutomationConfig(models.Model):
    """Флаги и контракт интеграции Битрикс24 ↔ Delayu (п.27–29)."""

    DEFAULT_FLAGS = {
        "bitrix_inbound": True,
        "bitrix_outbound": True,
        "bitrix_full_duplex": True,
        "smev_mock": True,
        "smev_live": False,
        "auto_package": True,
        "auto_smev": True,
        "auto_extract": True,
        "auto_fgistp": True,
        "auto_site_match": True,
        "auto_mo_tasks": True,
        "auto_tp_tasks": True,
        "auto_escalations": True,
        "gate_before_outbound": True,
        "rgis_connector": False,
        "isogd_connector": False,
        "sandbox": True,
        "opendata_mock": True,
        "opendata_live": False,
        "auto_opendata_investor": False,
        "auto_opendata_site": False,
    }

    subsystem = models.OneToOneField(
        "Subsystem", on_delete=models.CASCADE, related_name="invest_automation_config"
    )
    flags = models.JSONField(default=dict, blank=True)
    contract_version = models.CharField(max_length=16, default="v1")
    bitrix_webhook_token = models.CharField(max_length=128, blank=True)
    bitrix_api_base = models.URLField(blank=True)
    allowed_ips = models.JSONField(default=list, blank=True)
    field_mapping = models.JSONField(default=dict, blank=True)
    stage_mapping = models.JSONField(default=dict, blank=True)
    options = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_flags(self) -> dict:
        merged = dict(self.DEFAULT_FLAGS)
        merged.update(self.flags or {})
        return merged

    def flag(self, name: str, default: bool = False) -> bool:
        return bool(self.get_flags().get(name, default))

    def __str__(self):
        return f"InvestAutomationConfig({self.subsystem_id})"


class InvestIntegrationEvent(models.Model):
    """Единый журнал интеграций (п.26) + dead-letter/retry (п.19)."""

    class Direction(models.TextChoices):
        IN = "in", "Входящий"
        OUT = "out", "Исходящий"

    class Channel(models.TextChoices):
        BITRIX = "bitrix", "Битрикс24"
        SMEV = "smev", "СМЭВ"
        MO = "mo", "МО"
        TP = "tp", "ТП"
        INTERNAL = "internal", "Внутренний"

    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        DONE = "done", "Успех"
        ERROR = "error", "Ошибка"
        DEAD = "dead", "Dead-letter"
        SKIPPED = "skipped", "Пропущено"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="invest_integration_events"
    )
    project = models.ForeignKey(
        InvestProject, null=True, blank=True, on_delete=models.SET_NULL, related_name="integration_events"
    )
    site = models.ForeignKey(
        InvestSite, null=True, blank=True, on_delete=models.SET_NULL, related_name="integration_events"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    channel = models.CharField(max_length=16, choices=Channel.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    correlation_id = models.CharField(max_length=64, db_index=True)
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    event_type = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=512, blank=True)
    retries = models.PositiveSmallIntegerField(default=0)
    max_retries = models.PositiveSmallIntegerField(default=3)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["subsystem", "channel", "status"]),
            models.Index(fields=["external_id", "event_type"]),
        ]

    def __str__(self):
        return f"{self.channel}:{self.direction}:{self.correlation_id}"


class InvestExternalTask(models.Model):
    """Автозадачи МО / ТП (п.21–25)."""

    class Kind(models.TextChoices):
        MO = "mo", "Запрос МО"
        TP = "tp", "Запрос ТП"

    class Status(models.TextChoices):
        OPEN = "open", "Открыта"
        ANSWERED = "answered", "Ответ получен"
        AGREED = "agreed", "Согласовано"
        REJECTED = "rejected", "Отказ"
        OVERDUE = "overdue", "Просрочена"
        CANCELLED = "cancelled", "Отменена"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="invest_external_tasks"
    )
    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="external_tasks")
    organization = models.ForeignKey(
        "Organization", null=True, blank=True, on_delete=models.SET_NULL, related_name="invest_external_tasks"
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    title = models.CharField(max_length=255)
    due_at = models.DateTimeField(null=True, blank=True)
    escalated_level = models.PositiveSmallIntegerField(default=0)
    last_reminded_at = models.DateTimeField(null=True, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at", "-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"


class InvestAutomationRun(models.Model):
    """Снимок метрик автоматизации (п.30)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="invest_automation_runs"
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"AutomationRun#{self.pk}"


class InvestQuarterTarget(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_quarter_targets")
    year = models.PositiveSmallIntegerField("Год")
    quarter = models.PositiveSmallIntegerField("Квартал")
    attraction_goal = models.PositiveIntegerField("План новых проектов", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "year", "quarter")]
        ordering = ["-year", "-quarter"]

    def __str__(self):
        return f"{self.subsystem_id} Q{self.quarter}/{self.year}: {self.attraction_goal}"


class InvestProjectComment(models.Model):
    project = models.ForeignKey(InvestProject, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField("Комментарий")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Комментарий инвестпроекта"
        verbose_name_plural = "Комментарии инвестпроектов"

    def __str__(self):
        return f"{self.project.code}: {self.body[:40]}"


class InvestExtract(models.Model):
    """Выкопировка / ситуационный план по инвестплощадке."""

    class ExtractType(models.TextChoices):
        SITUATIONAL = "situational", "Ситуационный план"
        KPT = "kpt", "Выписка КПТ"
        BOUNDARY = "boundary", "Схема границ"
        OTHER = "other", "Прочее"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        REQUESTED = "requested", "Запрошена"
        RECEIVED = "received", "Получена"
        VERIFIED = "verified", "Проверена"
        ATTACHED = "attached", "Приложена"
        REJECTED = "rejected", "Отклонена"
        EXPIRED = "expired", "Просрочена"

    class GeometrySource(models.TextChoices):
        UPLOAD = "upload", "Файл"
        IMPORT = "import", "Импорт GeoJSON/KML"
        MOCK = "mock", "Mock-контур"
        SMEV_DERIVED = "smev_derived", "Из СМЭВ"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_extracts")
    site = models.ForeignKey(InvestSite, on_delete=models.CASCADE, related_name="extracts")
    project = models.ForeignKey(
        InvestProject,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="extracts",
    )
    extract_type = models.CharField(max_length=16, choices=ExtractType.choices, default=ExtractType.SITUATIONAL)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    cadastral_number = models.CharField("Кадастровый номер", max_length=64, blank=True)
    title = models.CharField("Наименование", max_length=255, blank=True)
    document_date = models.DateField("Дата документа", null=True, blank=True)
    valid_until = models.DateField("Действует до", null=True, blank=True)
    file = models.FileField(upload_to="invest/extracts/", blank=True)
    document = models.ForeignKey(
        "DocumentFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invest_extracts",
    )
    geometry = models.JSONField("Геометрия (GeoJSON)", default=dict, blank=True)
    geometry_source = models.CharField(
        max_length=16, choices=GeometrySource.choices, blank=True, default=""
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    external_ids = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "Выкопировка"
        verbose_name_plural = "Выкопировки"
        indexes = [
            models.Index(fields=["subsystem", "status"]),
            models.Index(fields=["site", "status"]),
        ]

    def __str__(self):
        return self.title or f"{self.get_extract_type_display()} · {self.cadastral_number or self.site_id}"

    @property
    def has_geometry(self) -> bool:
        return bool(self.geometry and (self.geometry.get("type") or self.geometry.get("coordinates")))


class InvestFgistpRecord(models.Model):
    """Сведения ФГИС ТП по инвестплощадке (mock / импорт, без live WFS)."""

    class RecordType(models.TextChoices):
        ZONES = "zones", "Зоны ТП"
        DOCUMENT = "document", "Документ ТП"
        OBJECTS = "objects", "Объекты"
        OTHER = "other", "Прочее"

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        REQUESTED = "requested", "Запрошены"
        RECEIVED = "received", "Получены"
        VERIFIED = "verified", "Проверены"
        ATTACHED = "attached", "Приложены"
        REJECTED = "rejected", "Отклонены"
        EXPIRED = "expired", "Просрочены"

    class GeometrySource(models.TextChoices):
        UPLOAD = "upload", "Файл"
        IMPORT = "import", "Импорт GeoJSON/KML"
        MOCK = "mock", "Mock-зоны"
        SMEV_DERIVED = "smev_derived", "Из СМЭВ"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="invest_fgistp_records")
    site = models.ForeignKey(InvestSite, on_delete=models.CASCADE, related_name="fgistp_records")
    project = models.ForeignKey(
        InvestProject,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fgistp_records",
    )
    record_type = models.CharField(max_length=16, choices=RecordType.choices, default=RecordType.ZONES)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    cadastral_number = models.CharField("Кадастровый номер", max_length=64, blank=True)
    title = models.CharField("Наименование", max_length=255, blank=True)
    document_date = models.DateField("Дата документа", null=True, blank=True)
    valid_until = models.DateField("Действует до", null=True, blank=True)
    file = models.FileField(upload_to="invest/fgistp/", blank=True)
    document = models.ForeignKey(
        "DocumentFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invest_fgistp_records",
    )
    payload = models.JSONField("Сведения (JSON)", default=dict, blank=True)
    geometry = models.JSONField("Геометрия (GeoJSON)", default=dict, blank=True)
    geometry_source = models.CharField(
        max_length=16, choices=GeometrySource.choices, blank=True, default=""
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    sla_due_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    external_ids = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-id"]
        verbose_name = "Сведения ФГИС ТП"
        verbose_name_plural = "Сведения ФГИС ТП"
        indexes = [
            models.Index(fields=["subsystem", "status"]),
            models.Index(fields=["site", "status"]),
        ]

    def __str__(self):
        return self.title or f"{self.get_record_type_display()} · {self.cadastral_number or self.site_id}"

    @property
    def has_geometry(self) -> bool:
        return bool(self.geometry and (self.geometry.get("type") or self.geometry.get("coordinates")))


class InvestFgistpDocument(models.Model):
    """Демо-каталог документов ФГИС ТП для поиска по адресу / КН."""

    class Level(models.TextChoices):
        FEDERAL = "federal", "Федеральный"
        REGIONAL = "regional", "Региональный"
        MUNICIPAL = "municipal", "Муниципальный"

    class DocType(models.TextChoices):
        STP = "stp", "Схема ТП"
        PZZ = "pzz", "ПЗЗ"
        SCHEME = "scheme", "Схема"
        OTHER = "other", "Прочее"

    subsystem = models.ForeignKey(
        "Subsystem",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="invest_fgistp_documents",
    )
    uin = models.CharField("UIN / внешний id", max_length=128)
    title = models.CharField("Наименование", max_length=512)
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.REGIONAL)
    doc_type = models.CharField(max_length=16, choices=DocType.choices, default=DocType.STP)
    address_text = models.TextField("Адрес / территория", blank=True)
    cadastral_numbers = models.JSONField("Кадастровые номера", default=list, blank=True)
    municipality_name = models.CharField("МО", max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    geometry = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Документ ФГИС ТП (каталог)"
        verbose_name_plural = "Документы ФГИС ТП (каталог)"
        constraints = [
            models.UniqueConstraint(
                fields=["subsystem", "uin"],
                name="uniq_invest_fgistp_doc_subsystem_uin",
            ),
        ]
        indexes = [
            models.Index(fields=["subsystem", "is_active"]),
            models.Index(fields=["level"]),
        ]

    def __str__(self):
        return self.title


class InvestMnpScheme(models.Model):
    """Локальная копия схемы ДТП МНП (Краснодарский край)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        READY = "ready", "Готово"
        ERROR = "error", "Ошибка"

    uin = models.CharField("UIN", max_length=64, unique=True, db_index=True)
    name = models.CharField("Наименование", max_length=512, blank=True)
    extent_raw = models.CharField("Extent 3857 raw", max_length=255, blank=True)
    extent_min_x = models.FloatField(null=True, blank=True)
    extent_min_y = models.FloatField(null=True, blank=True)
    extent_max_x = models.FloatField(null=True, blank=True)
    extent_max_y = models.FloatField(null=True, blank=True)
    feature_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    error_text = models.TextField(blank=True)
    synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "uin"]
        verbose_name = "Схема МНП (локальный store)"
        verbose_name_plural = "Схемы МНП (локальный store)"

    def __str__(self):
        return self.name or self.uin


class InvestMnpFeature(models.Model):
    """Локальная GeoJSON-фича генплана МНП (EPSG:4326)."""

    scheme = models.ForeignKey(
        InvestMnpScheme,
        on_delete=models.CASCADE,
        related_name="features",
    )
    external_id = models.CharField(max_length=128, blank=True, db_index=True)
    classid = models.CharField(max_length=32, db_index=True)
    class_name = models.CharField(max_length=255, blank=True)
    geom_type = models.CharField(max_length=8, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    geometry = models.JSONField("Геометрия GeoJSON 4326", default=dict, blank=True)
    bbox_min_lon = models.FloatField(db_index=True)
    bbox_min_lat = models.FloatField(db_index=True)
    bbox_max_lon = models.FloatField(db_index=True)
    bbox_max_lat = models.FloatField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Объект МНП (локальный store)"
        verbose_name_plural = "Объекты МНП (локальный store)"
        indexes = [
            models.Index(fields=["bbox_min_lon", "bbox_max_lon", "bbox_min_lat", "bbox_max_lat"]),
            models.Index(fields=["scheme", "classid"]),
        ]

    def __str__(self):
        return self.external_id or f"{self.classid}:{self.pk}"


class InvestMnpSyncRun(models.Model):
    """Журнал ручного sync локального store МНП."""

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    ok = models.BooleanField(default=False)
    stats = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Sync МНП store"
        verbose_name_plural = "Sync МНП store"

    def __str__(self):
        mark = "ok" if self.ok else "fail"
        return f"MNP sync {self.started_at:%Y-%m-%d %H:%M} ({mark})"


class InvestVerificationRun(models.Model):
    """Журнал проверки по открытым официальным источникам (Wave 1 / P0)."""

    class TargetType(models.TextChoices):
        INVESTOR = "investor", "Инвестор"
        PROJECT = "project", "Проект"
        SITE = "site", "Площадка"

    class Status(models.TextChoices):
        QUEUED = "queued", "В очереди"
        RUNNING = "running", "Выполняется"
        DONE = "done", "Готово"
        ERROR = "error", "Ошибка"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="invest_verification_runs"
    )
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    investor = models.ForeignKey(
        InvestInvestor,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="verification_runs",
    )
    project = models.ForeignKey(
        InvestProject,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="verification_runs",
    )
    site = models.ForeignKey(
        InvestSite,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="verification_runs",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    correlation_id = models.CharField(max_length=64, blank=True, db_index=True)
    summary = models.JSONField(default=dict, blank=True)
    error_text = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Проверка открытых данных"
        verbose_name_plural = "Проверки открытых данных"
        indexes = [
            models.Index(fields=["subsystem", "target_type", "-created_at"]),
        ]

    def __str__(self):
        return f"VerificationRun {self.target_type}:{self.pk} ({self.status})"


class InvestVerificationSourceResult(models.Model):
    """Результат одного источника внутри InvestVerificationRun."""

    class Status(models.TextChoices):
        OK = "ok", "OK"
        EMPTY = "empty", "Пусто"
        ERROR = "error", "Ошибка"
        SKIPPED = "skipped", "Пропущено"

    class Severity(models.TextChoices):
        INFO = "info", "Инфо"
        WARN = "warn", "Предупреждение"
        HARD = "hard", "Жёсткий"

    run = models.ForeignKey(
        InvestVerificationRun, on_delete=models.CASCADE, related_name="source_results"
    )
    source_code = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OK)
    severity = models.CharField(max_length=16, choices=Severity.choices, default=Severity.INFO)
    title = models.CharField(max_length=255, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    external_url = models.URLField(blank=True, max_length=512)
    error_text = models.TextField(blank=True)
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Результат источника"
        verbose_name_plural = "Результаты источников"
        indexes = [
            models.Index(fields=["run", "source_code"]),
        ]

    def __str__(self):
        return f"{self.source_code}:{self.status}"
