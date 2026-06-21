"""Прикладные модели платформы (этапы 1–10 ТЗ)."""
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone


class AppendOnlyError(PermissionError):
    """Запись журнала аудита нельзя изменить или удалить."""


class AuditLogQuerySet(models.QuerySet):
    def delete(self):
        raise AppendOnlyError("Журнал аудита append-only: массовое удаление запрещено.")

    def update(self, **kwargs):
        raise AppendOnlyError("Журнал аудита append-only: изменение записей запрещено.")


class AuditLogManager(models.Manager):
    def get_queryset(self):
        return AuditLogQuerySet(self.model, using=self._db)


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    subsystem = models.ForeignKey(
        "Subsystem", null=True, on_delete=models.CASCADE, related_name="audit_logs"
    )
    action = models.CharField(max_length=64)
    model_name = models.CharField(max_length=128, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = AuditLogManager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись аудита"
        verbose_name_plural = "Журнал аудита"

    def save(self, *args, **kwargs):
        if self.pk:
            raise AppendOnlyError("Журнал аудита append-only: изменение записей запрещено.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("Журнал аудита append-only: удаление записей запрещено.")


class UserProfile(models.Model):
    """Расширенный профиль сотрудника (M03) — не менее 30 атрибутов помимо User."""

    class Gender(models.TextChoices):
        MALE = "m", "Мужской"
        FEMALE = "f", "Женский"
        UNSPECIFIED = "u", "Не указан"

    class EmploymentType(models.TextChoices):
        STAFF = "staff", "Штат"
        CONTRACT = "contract", "Договор"
        PART_TIME = "part", "Совместительство"
        INTERN = "intern", "Стажёр"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delayu_profile"
    )
    # Контакты
    phone = models.CharField("Телефон основной", max_length=32, blank=True)
    phone_mobile = models.CharField("Мобильный", max_length=32, blank=True)
    phone_work = models.CharField("Рабочий", max_length=32, blank=True)
    phone_internal = models.CharField("Внутренний", max_length=16, blank=True)
    email_personal = models.EmailField("Личный e-mail", blank=True)
    telegram = models.CharField("Telegram", max_length=64, blank=True)
    telegram_chat_id = models.CharField(
        "Telegram chat_id",
        max_length=32,
        blank=True,
        help_text="Числовой chat_id для Telegram Bot API (приоритетнее @username)",
    )
    uzhv_push_subscription = models.JSONField(
        "UZHV Web Push",
        default=dict,
        blank=True,
        help_text="Web Push subscription (endpoint, keys) для АИС УЖВ",
    )
    # Адреса
    address_registration = models.CharField("Адрес регистрации", max_length=500, blank=True)
    address_residence = models.CharField("Адрес проживания", max_length=500, blank=True)
    # Личные данные
    middle_name = models.CharField("Отчество", max_length=150, blank=True)
    gender = models.CharField(
        "Пол", max_length=1, choices=Gender.choices, default=Gender.UNSPECIFIED
    )
    birth_date = models.DateField("Дата рождения", null=True, blank=True)
    snils = models.CharField("СНИЛС", max_length=14, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    passport_series = models.CharField("Серия паспорта", max_length=8, blank=True)
    passport_number = models.CharField("Номер паспорта", max_length=16, blank=True)
    passport_issued_by = models.CharField("Кем выдан", max_length=255, blank=True)
    passport_issued_date = models.DateField("Дата выдачи", null=True, blank=True)
    # Работа
    employee_number = models.CharField("Табельный/личный №", max_length=32, blank=True)
    tab_number = models.CharField("Табельный номер", max_length=32, blank=True)
    position_title = models.CharField("Должность (текст)", max_length=255, blank=True)
    hire_date = models.DateField("Дата приёма", null=True, blank=True)
    dismissal_date = models.DateField("Дата увольнения", null=True, blank=True)
    employment_type = models.CharField(
        "Тип занятости",
        max_length=16,
        choices=EmploymentType.choices,
        default=EmploymentType.STAFF,
    )
    department_text = models.CharField("Подразделение (текст)", max_length=255, blank=True)
    manager_name = models.CharField("Руководитель", max_length=255, blank=True)
    # Система
    timezone = models.CharField("Часовой пояс", max_length=64, default="Europe/Moscow")
    locale = models.CharField("Язык", max_length=8, default="ru")
    comment = models.TextField("Примечание", blank=True)
    must_change_password = models.BooleanField("Сменить пароль при входе", default=False)
    two_factor_enabled = models.BooleanField("2FA", default=False)
    totp_secret = models.CharField("TOTP secret", max_length=64, blank=True)
    pii_consent_at = models.DateTimeField("Согласие на обработку ПДн", null=True, blank=True)
    theme_prefs = models.JSONField(default=dict, blank=True)
    onboarding_state = models.JSONField(
        default=dict,
        blank=True,
        help_text="Прогресс онбординга (#50): steps, dismissed_at",
    )
    active_subsystem = models.ForeignKey(
        "Subsystem", null=True, blank=True, on_delete=models.SET_NULL
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Профиль пользователя"
        verbose_name_plural = "Профили пользователей"

    def full_name(self):
        parts = [self.user.last_name, self.user.first_name, self.middle_name]
        return " ".join(p for p in parts if p).strip() or self.user.username

    @classmethod
    def attribute_groups(cls):
        """Группы атрибутов для карточки и ТЗ (≥30 полей)."""
        return PROFILE_ATTRIBUTE_GROUPS


PROFILE_ATTRIBUTE_GROUPS = [
    {
        "title": "Учётная запись",
        "fields": [
            ("username", "Логин"),
            ("email", "E-mail (рабочий)"),
            ("is_active", "Активен"),
            ("last_login", "Последний вход"),
        ],
    },
    {
        "title": "ФИО и личные данные",
        "fields": [
            ("last_name", "Фамилия"),
            ("first_name", "Имя"),
            ("middle_name", "Отчество"),
            ("gender", "Пол"),
            ("birth_date", "Дата рождения"),
            ("snils", "СНИЛС"),
            ("inn", "ИНН"),
        ],
    },
    {
        "title": "Паспорт",
        "fields": [
            ("passport_series", "Серия"),
            ("passport_number", "Номер"),
            ("passport_issued_by", "Кем выдан"),
            ("passport_issued_date", "Дата выдачи"),
        ],
    },
    {
        "title": "Контакты",
        "fields": [
            ("phone", "Телефон"),
            ("phone_mobile", "Мобильный"),
            ("phone_work", "Рабочий"),
            ("phone_internal", "Внутренний"),
            ("email_personal", "Личный e-mail"),
            ("telegram", "Telegram"),
            ("telegram_chat_id", "Telegram chat_id"),
        ],
    },
    {
        "title": "Адреса",
        "fields": [
            ("address_registration", "Регистрация"),
            ("address_residence", "Проживание"),
        ],
    },
    {
        "title": "Работа",
        "fields": [
            ("employee_number", "Личный №"),
            ("tab_number", "Табельный №"),
            ("position_title", "Должность"),
            ("employment_type", "Тип занятости"),
            ("hire_date", "Дата приёма"),
            ("dismissal_date", "Дата увольнения"),
            ("department_text", "Подразделение"),
            ("manager_name", "Руководитель"),
        ],
    },
    {
        "title": "Система и безопасность",
        "fields": [
            ("timezone", "Часовой пояс"),
            ("locale", "Язык"),
            ("must_change_password", "Смена пароля"),
            ("two_factor_enabled", "2FA"),
            ("comment", "Примечание"),
        ],
    },
]


class Department(models.Model):
    organization = models.ForeignKey(
        "Organization", on_delete=models.CASCADE, related_name="departments"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children"
    )
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        unique_together = [("organization", "code")]
        verbose_name = "Подразделение"
        verbose_name_plural = "Подразделения"


class Position(models.Model):
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="positions")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    headcount = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = [("department", "code")]
        verbose_name = "Должность"


class UserAssignment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="assignments"
    )
    department = models.ForeignKey(Department, on_delete=models.CASCADE)
    position = models.ForeignKey(Position, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Назначение в ШР"


class Delegation(models.Model):
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delegations_given"
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delegations_received"
    )
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE)
    start_at = models.DateField()
    end_at = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Делегирование"


class UserSession(models.Model):
    """Журнал веб-сессий (#14)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="platform_sessions"
    )
    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        verbose_name = "Сессия пользователя"
        verbose_name_plural = "Сессии пользователей"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class CaseFile(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_PROGRESS = "in_progress", "В работе"
        WAITING = "waiting", "Ожидание"
        DONE = "done", "Исполнено"
        ARCHIVED = "archived", "В архиве"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="cases")
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    number = models.CharField(max_length=32, db_index=True)
    title = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_cases",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_cases"
    )
    due_date = models.DateField(null=True, blank=True)
    priority = models.PositiveSmallIntegerField(default=2)
    description = models.TextField(blank=True)
    extra_data = models.JSONField(default=dict, blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_cases",
        verbose_name="Кто передал в архив",
    )
    archive_reason = models.TextField("Основание / примечание к архиву", blank=True)
    retention_until = models.DateField("Срок хранения до", null=True, blank=True)
    legal_hold = models.BooleanField("Legal hold (запрет уничтожения)", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "number")]
        ordering = ["-updated_at"]
        verbose_name = "Дело"
        verbose_name_plural = "Дела"


class RegistryType(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="registry_types")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    field_schema = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("subsystem", "code")]
        ordering = ["sort_order", "name"]
        verbose_name = "Тип реестра"


class RegistryRecord(models.Model):
    registry_type = models.ForeignKey(
        RegistryType, on_delete=models.CASCADE, related_name="records"
    )
    organization = models.ForeignKey("Organization", on_delete=models.CASCADE)
    external_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запись реестра"


class DocumentFile(models.Model):
    class DocType(models.TextChoices):
        ATTACHMENT = "attachment", "Вложение"
        INCOMING = "incoming", "Входящий"
        OUTGOING = "outgoing", "Исходящий"
        INTERNAL = "internal", "Служебная записка"
        CONTRACT = "contract", "Договор"
        SCAN = "scan", "Скан"
        OTHER = "other", "Прочее"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="documents")
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.CASCADE, related_name="documents"
    )
    root_document = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="version_chain",
        verbose_name="Корневая версия",
    )
    title = models.CharField(max_length=255)
    doc_type = models.CharField(
        "Тип документа",
        max_length=32,
        choices=DocType.choices,
        default=DocType.ATTACHMENT,
    )
    description = models.TextField("Описание", blank=True)
    file = models.FileField(upload_to="documents/%Y/%m/")
    content_sha256 = models.CharField("SHA-256", max_length=64, blank=True, db_index=True)
    version = models.PositiveIntegerField(default=1)
    is_current = models.BooleanField("Актуальная версия", default=True, db_index=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    is_signed = models.BooleanField(default=False)
    signature_meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def get_root(self):
        return self.root_document or self

    def version_siblings(self):
        root = self.get_root()
        return DocumentFile.objects.filter(
            models.Q(pk=root.pk) | models.Q(root_document_id=root.pk)
        ).order_by("-version")


class Correspondence(models.Model):
    class Direction(models.TextChoices):
        IN = "in", "Входящее"
        OUT = "out", "Исходящее"

    class Status(models.TextChoices):
        REGISTERED = "registered", "Зарегистрировано"
        IN_WORK = "in_work", "В работе"
        SENT = "sent", "Отправлено"
        CLOSED = "closed", "Закрыто"

    class MailLabel(models.TextChoices):
        WORK = "work", "Личное"
        COMPANY = "company", "Служебное"
        IMPORTANT = "important", "Важное"
        PRIVATE = "private", "Конфиденциально"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="correspondence"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    reg_number = models.CharField(max_length=64, db_index=True)
    reg_date = models.DateField(default=timezone.now)
    subject = models.CharField(max_length=500)
    counterparty = models.CharField(max_length=255, blank=True)
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="correspondence"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REGISTERED)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="correspondence_created"
    )
    linked_incoming = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outgoing_replies",
        verbose_name="Связанное входящее",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField("Прочитано", default=False)
    is_starred = models.BooleanField("В избранном", default=False)
    is_deleted = models.BooleanField("В корзине", default=False)
    deleted_at = models.DateTimeField("Удалено", null=True, blank=True)
    is_draft = models.BooleanField("Черновик", default=False)
    is_spam = models.BooleanField("Спам", default=False)
    mail_label = models.CharField(
        "Метка",
        max_length=20,
        choices=MailLabel.choices,
        blank=True,
    )

    class Meta:
        ordering = ["-reg_date", "-reg_number"]
        verbose_name = "Корреспонденция"


class CorrespondenceRoute(models.Model):
    """M27 — переадресация / маршрутизация."""

    correspondence = models.ForeignKey(
        Correspondence, on_delete=models.CASCADE, related_name="routes"
    )
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="routes_sent",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="routes_received",
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Маршрут корреспонденции"


class CorrespondenceEvent(models.Model):
    """M28 — история событий по корреспонденции и связанным документам."""

    class EventType(models.TextChoices):
        REGISTERED = "registered", "Регистрация"
        ROUTED = "routed", "Переадресация"
        STATUS = "status", "Смена статуса"
        LINKED = "linked", "Связь с делом"
        SIGNED = "signed", "Подпись"
        VERSION = "version", "Новая версия"
        COMMENT = "comment", "Комментарий"

    correspondence = models.ForeignKey(
        Correspondence, on_delete=models.CASCADE, related_name="events"
    )
    document = models.ForeignKey(
        "DocumentFile",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="correspondence_events",
    )
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    description = models.CharField(max_length=500)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Событие корреспонденции"


class PrintTemplate(models.Model):
    """M29 — шаблон печатной формы."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="print_templates"
    )
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    body = models.TextField(
        help_text="Плейсхолдеры: {{reg_number}}, {{subject}}, {{counterparty}}, {{reg_date}}"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Печатная форма"


class RegistrationJournalEntry(models.Model):
    correspondence = models.OneToOneField(
        Correspondence, on_delete=models.CASCADE, related_name="journal_entry"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        verbose_name = "Журнал регистрации"


class TaskItem(models.Model):
    class KanbanColumn(models.TextChoices):
        BACKLOG = "backlog", "Очередь"
        TODO = "todo", "К выполнению"
        IN_PROGRESS = "in_progress", "В работе"
        REVIEW = "review", "Проверка"
        DONE = "done", "Готово"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="tasks")
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks"
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, default="open")
    kanban_column = models.CharField(
        max_length=20, choices=KanbanColumn.choices, default=KanbanColumn.TODO
    )
    due_date = models.DateField(null=True, blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    priority = models.PositiveSmallIntegerField(default=2)
    start_date = models.DateField("Дата начала", null=True, blank=True)
    duration_days = models.PositiveSmallIntegerField("Длительность (дней)", default=1)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["kanban_column", "-priority", "due_date"]
        verbose_name = "Задача"

    @property
    def gantt_end_date(self):
        from datetime import timedelta

        start = self.start_date or self.due_date
        if not start:
            return None
        return start + timedelta(days=max(1, self.duration_days) - 1)


class Notification(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Информация"
        WARNING = "warning", "Важно"
        URGENT = "urgent", "Срочно"
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delayu_notifications"
    )
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=500, blank=True)
    level = models.CharField(
        "Уровень", max_length=16, choices=Level.choices, default=Level.INFO
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Comment(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE)
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    document = models.ForeignKey(
        DocumentFile, null=True, blank=True, on_delete=models.CASCADE, related_name="comments"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="replies",
    )
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Комментарий"


class ChatRoom(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="chat_rooms")
    case = models.ForeignKey(CaseFile, null=True, blank=True, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name="chat_rooms", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Чат"


class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class Mention(models.Model):
    """M39 — упоминание @username в комментарии или чате."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="mentions")
    mentioned_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentions_received",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mentions_sent",
    )
    comment = models.ForeignKey(
        Comment, null=True, blank=True, on_delete=models.CASCADE, related_name="mentions"
    )
    chat_message = models.ForeignKey(
        ChatMessage, null=True, blank=True, on_delete=models.CASCADE, related_name="mentions"
    )
    excerpt = models.CharField(max_length=200, blank=True)
    link_path = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Упоминание"


class ObjectSubscription(models.Model):
    """M39 — подписка на изменения объекта."""

    class TargetType(models.TextChoices):
        CASE = "case", "Дело"
        DOCUMENT = "document", "Документ"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="object_subscriptions"
    )
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE)
    target_type = models.CharField(max_length=16, choices=TargetType.choices)
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.CASCADE, related_name="subscriptions"
    )
    document = models.ForeignKey(
        DocumentFile,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Подписка на объект"


class VideoMeeting(models.Model):
    """M40 — видеосовещание (ссылка ВКС + протокол)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="video_meetings"
    )
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="meetings"
    )
    title = models.CharField(max_length=255)
    meeting_url = models.URLField(max_length=500, blank=True)
    scheduled_at = models.DateTimeField()
    protocol_notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="meetings_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-scheduled_at"]
        verbose_name = "Видеосовещание"


class MessengerChannel(models.Model):
    """M41 — канал уведомлений во внешний мессенджер (демо-конфиг)."""

    class ChannelType(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        MAX = "max", "MAX"
        OTHER = "other", "Другое"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="messenger_channels"
    )
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    channel_type = models.CharField(max_length=16, choices=ChannelType.choices)
    webhook_url = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Канал мессенджера"


class BPMTemplate(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="bpm_templates")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    steps = models.JSONField(default=list)
    diagram = models.JSONField("Диаграмма BPM", default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Шаблон BPM"


class BPMInstance(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        COMPLETED = "completed", "Завершён"
        REJECTED = "rejected", "Отклонён"

    template = models.ForeignKey(BPMTemplate, on_delete=models.PROTECT)
    case = models.ForeignKey(CaseFile, on_delete=models.CASCADE, related_name="bpm_instances")
    current_step_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Экземпляр процесса"


class BPMTask(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        DONE = "done", "Согласовано"
        REJECTED = "rejected", "Отклонено"

    instance = models.ForeignKey(BPMInstance, on_delete=models.CASCADE, related_name="tasks")
    step_id = models.CharField(max_length=64)
    step_name = models.CharField(max_length=255)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    comment = models.TextField(blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Задача согласования"


class SLARule(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="sla_rules")
    code = models.SlugField(max_length=64, default="default")
    name = models.CharField(max_length=255, default="Стандартный SLA")
    case_kind = models.CharField(max_length=64, default="default")
    hours_limit = models.PositiveIntegerField(default=72)
    is_active = models.BooleanField(default=True)
    escalate_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sla_escalations",
        verbose_name="Эскалация к",
    )

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Правило SLA"


class CaseRegulation(models.Model):
    """M36 — регламентные сроки по типам дел."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="case_regulations"
    )
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    default_working_days = models.PositiveIntegerField(default=30)
    applies_on_status = models.CharField(
        max_length=20, choices=CaseFile.Status.choices, blank=True
    )
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Регламент сроков"


class ReportTemplate(models.Model):
    class ReportKind(models.TextChoices):
        STANDARD = "standard", "Стандартный"
        REGULATORY = "regulatory", "Регламентированный"
        CHART = "chart", "График"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="reports")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    query_key = models.CharField(max_length=64)
    columns = models.JSONField(default=list)
    report_kind = models.CharField(
        max_length=16,
        choices=ReportKind.choices,
        default=ReportKind.STANDARD,
        verbose_name="Тип отчёта",
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    default_period_days = models.PositiveSmallIntegerField(
        "Период по умолчанию (дней)", default=30
    )

    class Meta:
        unique_together = [("subsystem", "code")]


class ReportRun(models.Model):
    template = models.ForeignKey(ReportTemplate, on_delete=models.CASCADE, related_name="runs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    result = models.JSONField(default=dict)
    period_label = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ReportSchedule(models.Model):
    """#31 — расписание автоматического формирования отчётов."""

    class Frequency(models.TextChoices):
        DAILY = "daily", "Ежедневно"
        WEEKLY = "weekly", "Еженедельно"
        MONTHLY = "monthly", "Ежемесячно"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="report_schedules"
    )
    template = models.ForeignKey(
        ReportTemplate, on_delete=models.CASCADE, related_name="schedules"
    )
    frequency = models.CharField(max_length=16, choices=Frequency.choices, default=Frequency.DAILY)
    run_hour = models.PositiveSmallIntegerField(default=6, verbose_name="Час запуска (0–23)")
    run_weekday = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="0=пн … 6=вс (для weekly)"
    )
    run_day = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="День месяца 1–28 (для monthly)"
    )
    period_days = models.PositiveSmallIntegerField(default=30)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Расписание отчёта"


class RegulatoryReportSubmission(models.Model):
    """M17 — сдача регламентированной формы за период."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED = "submitted", "Сдано"
        APPROVED = "approved", "Принято"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="regulatory_reports"
    )
    form_code = models.CharField(max_length=64)
    form_name = models.CharField(max_length=255)
    period_label = models.CharField(max_length=32, help_text="Напр. 2026-05 или 2026-Q1")
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    version = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    indicators = models.JSONField(default=dict, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="regulatory_submissions",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_label", "-version"]
        verbose_name = "Регламентированная отчётность"


class IntegrationEndpoint(models.Model):
    """M42 — шлюз; M44/M45 — типы smev / external."""

    class EndpointType(models.TextChoices):
        GATEWAY = "gateway", "Шлюз"
        SMEV = "smev", "СМЭВ"
        REST = "rest", "REST"
        EXTERNAL_1C = "external_1c", "1С"
        EXTERNAL_GIS = "external_gis", "ГИС ЖКХ"
        MAIL = "mail", "Почта"
        WEBHOOK = "webhook", "Webhook"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="integrations"
    )
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    endpoint_type = models.CharField(max_length=32, choices=EndpointType.choices)
    config = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    max_retries = models.PositiveSmallIntegerField(default=3)

    class Meta:
        unique_together = [("subsystem", "code")]
        verbose_name = "Коннектор интеграции"


class IntegrationMessage(models.Model):
    class Direction(models.TextChoices):
        IN = "in", "Входящее"
        OUT = "out", "Исходящее"

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        SENT = "sent", "Отправлено"
        RECEIVED = "received", "Получено"
        FAILED = "failed", "Ошибка"
        DEAD_LETTER = "dead_letter", "Dead letter"

    endpoint = models.ForeignKey(
        IntegrationEndpoint, on_delete=models.CASCADE, related_name="messages"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    error_text = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    external_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Сообщение интеграции"


class ApiClientKey(models.Model):
    """M43 — ключ доступа к REST API."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="api_keys"
    )
    name = models.CharField(max_length=128)
    key_prefix = models.CharField(max_length=16, db_index=True)
    key_hash = models.CharField(max_length=64)
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)
    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API-ключ"


class KnowledgeArticle(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="knowledge")
    title = models.CharField(max_length=255)
    body = models.TextField()
    tags = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Статья базы знаний"
        ordering = ["title"]


class SearchIndexEntry(models.Model):
    """Полнотекстовый индекс для гибридного / семантического поиска (pgvector-ready)."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="search_index")
    kind = models.CharField(max_length=32, db_index=True)
    object_id = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    body = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    embedding = models.JSONField(default=list, blank=True)
    indexed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "kind", "object_id")]
        ordering = ["-indexed_at"]
        verbose_name = "Поисковый индекс"
        verbose_name_plural = "Поисковый индекс"


class AiRequestLog(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="ai_logs")
    module_code = models.CharField(max_length=8)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    prompt = models.TextField()
    response = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AudioArchiveItem(models.Model):
    class SourceType(models.TextChoices):
        CALL = "call", "Звонок"
        MEETING = "meeting", "Совещание"
        OTHER = "other", "Прочее"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="audio_items")
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="audio_items"
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="audio/%Y/%m/", blank=True)
    source_type = models.CharField(
        max_length=16, choices=SourceType.choices, default=SourceType.CALL
    )
    duration_sec = models.PositiveIntegerField(default=0)
    transcript = models.TextField(blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
    retention_until = models.DateField(null=True, blank=True, verbose_name="Хранить до")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audio_uploaded",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Аудиозапись"
        ordering = ["-recorded_at", "-created_at"]


class AiPolicy(models.Model):
    """M66 — политики ИИ (лимиты, модель, ПДн)."""

    subsystem = models.OneToOneField(
        "Subsystem", on_delete=models.CASCADE, related_name="ai_policy"
    )
    model_name = models.CharField(max_length=64, default="demo-local")
    max_requests_per_day = models.PositiveIntegerField(default=500)
    allow_pii = models.BooleanField(default=False, verbose_name="Разрешить ПДн в промптах")
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Политика ИИ"


class AiFeedback(models.Model):
    """#45 — обратная связь по результатам ИИ."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="ai_feedback")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    module_code = models.CharField(max_length=8, default="M47")
    rating = models.PositiveSmallIntegerField(default=3)
    comment = models.TextField(blank=True)
    prompt_excerpt = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Отзыв об ИИ"


class AiHumanReview(models.Model):
    """#42 — HITL: проверка человеком результата ИИ."""

    class Status(models.TextChoices):
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Утверждено"
        REJECTED = "rejected", "Отклонено"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="ai_reviews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ai_reviews_created",
    )
    module_code = models.CharField(max_length=8, default="M47")
    title = models.CharField(max_length=255)
    ai_output = models.TextField()
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="ai_reviews_done",
    )
    review_comment = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Проверка ИИ (HITL)"


class SignatureRequest(models.Model):
    """#37 — запрос на подписание КЭП (mock/real adapter)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        SENT = "sent", "Отправлено в КЭП"
        SIGNED = "signed", "Подписано"
        FAILED = "failed", "Ошибка"
        REJECTED = "rejected", "Отклонено"

    document = models.ForeignKey(
        "DocumentFile", on_delete=models.CASCADE, related_name="signature_requests"
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="signature_requests"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    provider = models.CharField(max_length=64, default="mock")
    external_id = models.CharField(max_length=128, blank=True)
    error_text = models.TextField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Запрос КЭП"


class GeoLayer(models.Model):
    """M67 — слой геопортала."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="geo_layers")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=16, default="#666cff")
    is_visible = models.BooleanField(default=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        ordering = ["name"]
        verbose_name = "ГИС-слой"

    def __str__(self):
        return self.name


class GeoObject(models.Model):
    """M67 — объект на карте."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="geo_objects")
    layer = models.ForeignKey(GeoLayer, on_delete=models.CASCADE, related_name="geo_objects")
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="geo_objects"
    )
    title = models.CharField(max_length=255)
    address = models.CharField(max_length=500, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["title"]
        verbose_name = "Геообъект"

    def __str__(self):
        return self.title


class PwaDevice(models.Model):
    """M68 — зарегистрированное мобильное устройство."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="pwa_devices")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="pwa_devices"
    )
    device_label = models.CharField(max_length=128)
    app_version = models.CharField(max_length=32, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_sync_at", "device_label"]
        verbose_name = "PWA-устройство"

    def __str__(self):
        return self.device_label


class PwaDraft(models.Model):
    """M68 — офлайн-черновик полевого наряда."""

    device = models.ForeignKey(PwaDevice, on_delete=models.CASCADE, related_name="drafts")
    title = models.CharField(max_length=255)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "PWA-черновик"


class SsoProvider(models.Model):
    """M69 — провайдер единого входа."""

    class ProviderType(models.TextChoices):
        ESIA = "esia", "ЕСИА"
        SAML = "saml", "SAML 2.0"
        OIDC = "oidc", "OpenID Connect"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="sso_providers")
    name = models.CharField(max_length=255)
    provider_type = models.CharField(max_length=16, choices=ProviderType.choices, default=ProviderType.ESIA)
    client_id = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "SSO-провайдер"

    def __str__(self):
        return self.name


class EtlJob(models.Model):
    """M70 — задание массовой загрузки."""

    class SourceType(models.TextChoices):
        CSV = "csv", "CSV"
        XLSX = "xlsx", "Excel"
        DB = "db", "База данных"
        API = "api", "REST API"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="etl_jobs")
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=16, choices=SourceType.choices, default=SourceType.CSV)
    schedule_cron = models.CharField(max_length=64, blank=True, verbose_name="Расписание (cron)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "ETL-задание"

    def __str__(self):
        return self.name


class EtlRun(models.Model):
    """M70 — запуск ETL."""

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успех"
        FAILED = "failed", "Ошибка"

    job = models.ForeignKey(EtlJob, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    rows_ok = models.PositiveIntegerField(default=0)
    rows_err = models.PositiveIntegerField(default=0)
    error_rows = models.JSONField(
        default=list,
        blank=True,
        help_text="Протокол ошибок по строкам (#32)",
    )
    log = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Запуск ETL"


class DataDataset(models.Model):
    """M71 — набор витрины данных."""

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="data_datasets")
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64)
    description = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    row_count = models.PositiveIntegerField(default=0)
    schema = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "slug")]
        ordering = ["name"]
        verbose_name = "Набор данных"

    def __str__(self):
        return self.name


class CitizenAppeal(models.Model):
    """M72 — обращение с портала гражданина."""

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_PROGRESS = "in_progress", "В работе"
        ANSWERED = "answered", "Ответ дан"
        CLOSED = "closed", "Закрыто"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="citizen_appeals")
    public_id = models.CharField(max_length=32)
    applicant_name = models.CharField(max_length=255)
    subject = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="citizen_appeals"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "public_id")]
        ordering = ["-created_at"]
        verbose_name = "Обращение гражданина"

    def __str__(self):
        return f"{self.public_id} — {self.subject[:40]}"


class NSIClassifier(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="nsi_classifiers")
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [("subsystem", "code")]
        ordering = ["name"]
        verbose_name = "Справочник НСИ"

    def __str__(self):
        return self.name


class NSIValue(models.Model):
    classifier = models.ForeignKey(NSIClassifier, on_delete=models.CASCADE, related_name="values")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        unique_together = [("classifier", "code")]
        ordering = ["sort_order", "name"]
        verbose_name = "Значение НСИ"

    def __str__(self):
        return f"{self.code} — {self.name}"


class FormSchema(models.Model):
    """M74 — схема полей карточки."""

    class Target(models.TextChoices):
        CASE = "case", "Дело"
        REGISTRY = "registry", "Реестр"
        CORRESPONDENCE = "correspondence", "Корреспонденция"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="form_schemas")
    target = models.CharField(max_length=32, choices=Target.choices, default=Target.CASE)
    code = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, default="")
    schema = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "target", "code")]
        ordering = ["target", "code"]
        verbose_name = "Схема формы"

    def __str__(self):
        return self.name or self.code


class BulkOperation(models.Model):
    """M75 — журнал массовых операций."""

    class Operation(models.TextChoices):
        STATUS = "status", "Смена статуса"
        ASSIGN = "assign", "Назначение исполнителя"
        EXPORT = "export", "Экспорт выборки"

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        SUCCESS = "success", "Выполнено"
        FAILED = "failed", "Ошибка"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="bulk_operations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    operation = models.CharField(max_length=16, choices=Operation.choices)
    target_module = models.CharField(max_length=8, default="M22")
    filter_params = models.JSONField(default=dict, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    affected_count = models.PositiveIntegerField(default=0)
    log = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Массовая операция"


class ExportJob(models.Model):
    """M76 — выгрузка / печать."""

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        SUCCESS = "success", "Готово"
        FAILED = "failed", "Ошибка"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="export_jobs")
    kind = models.CharField(max_length=64)
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    params = models.JSONField(default=dict, blank=True)
    records_count = models.PositiveIntegerField(default=0)
    result_file = models.FileField(upload_to="exports/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Выгрузка"


class ManagementDirective(models.Model):
    """M77 — поручение руководства."""

    class Status(models.TextChoices):
        ISSUED = "issued", "Выдано"
        IN_PROGRESS = "in_progress", "В исполнении"
        DONE = "done", "Исполнено"
        OVERDUE = "overdue", "Просрочено"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="directives")
    number = models.CharField(max_length=32)
    title = models.CharField(max_length=500)
    instruction = models.TextField(blank=True)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_directives",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="authored_directives",
    )
    case = models.ForeignKey(
        CaseFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="directives"
    )
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED)
    report_text = models.TextField(blank=True)
    reported_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("subsystem", "number")]
        ordering = ["-created_at"]
        verbose_name = "Поручение"

    def __str__(self):
        return f"{self.number} — {self.title[:40]}"


class NotificationTemplate(models.Model):
    """M78 — шаблон уведомления по событию."""

    class Channel(models.TextChoices):
        IN_APP = "in_app", "В приложении"
        EMAIL = "email", "E-mail"
        SMS = "sms", "SMS"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="notification_templates"
    )
    event_code = models.SlugField(max_length=64)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.IN_APP)
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("subsystem", "event_code", "channel")]
        ordering = ["event_code", "channel"]
        verbose_name = "Шаблон уведомления"

    def __str__(self):
        return f"{self.event_code} ({self.get_channel_display()})"


class MailTransportConfig(models.Model):
    """SMTP/IMAP для подсистемы (M45 / эксплуатация)."""

    subsystem = models.OneToOneField(
        "Subsystem",
        on_delete=models.CASCADE,
        related_name="mail_transport",
    )
    is_enabled = models.BooleanField("Почта включена", default=False)
    default_from_email = models.EmailField("Отправитель (From)", blank=True)
    smtp_host = models.CharField("SMTP хост", max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField("SMTP порт", default=587)
    smtp_use_tls = models.BooleanField("SMTP TLS", default=True)
    smtp_username = models.CharField(max_length=255, blank=True)
    smtp_password = models.CharField(max_length=255, blank=True)
    imap_enabled = models.BooleanField("Приём IMAP", default=False)
    imap_host = models.CharField("IMAP хост", max_length=255, blank=True)
    imap_port = models.PositiveIntegerField("IMAP порт", default=993)
    imap_use_ssl = models.BooleanField("IMAP SSL", default=True)
    imap_username = models.CharField(max_length=255, blank=True)
    imap_password = models.CharField(max_length=255, blank=True)
    imap_folder = models.CharField("Папка IMAP", max_length=128, default="INBOX")
    last_inbound_sync = models.DateTimeField("Последняя синхронизация", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Почтовый транспорт"
        verbose_name_plural = "Почтовые транспорты"


class MailDeliveryLog(models.Model):
    """Журнал отправки и приёма писем."""

    class Direction(models.TextChoices):
        OUTBOUND = "out", "Исходящее"
        INBOUND = "in", "Входящее"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="mail_logs"
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    recipient = models.CharField(max_length=255, blank=True)
    sender = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    event_code = models.SlugField(max_length=64, blank=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    correspondence = models.ForeignKey(
        "Correspondence",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mail_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Журнал почты"


class AvScanResult(models.Model):
    """M79 — результат антивирусной проверки."""

    class Status(models.TextChoices):
        PENDING = "pending", "В очереди"
        CLEAN = "clean", "Чисто"
        INFECTED = "infected", "Угроза"
        ERROR = "error", "Ошибка сканера"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="av_scans")
    document = models.ForeignKey(
        DocumentFile, null=True, blank=True, on_delete=models.SET_NULL, related_name="av_scans"
    )
    filename = models.CharField(max_length=500)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    threat_name = models.CharField(max_length=255, blank=True)
    scanned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Проверка AV"


class PiiMaskingPolicy(models.Model):
    """M80 — политика маскирования ПДн."""

    subsystem = models.OneToOneField(
        "Subsystem", on_delete=models.CASCADE, related_name="pii_policy"
    )
    demo_mode = models.BooleanField(default=False, verbose_name="Режим демонстрации")
    mask_passport = models.BooleanField(default=True)
    mask_phone = models.BooleanField(default=True)
    mask_email = models.BooleanField(default=True)
    masked_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="Коды ролей, для которых поля скрыты",
    )
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Политика ПДн"


class DataRetentionPolicy(models.Model):
    """#9 — политика сроков хранения архивных дел."""

    subsystem = models.OneToOneField(
        "Subsystem", on_delete=models.CASCADE, related_name="retention_policy"
    )
    default_archive_years = models.PositiveSmallIntegerField(
        default=5, verbose_name="Срок хранения в архиве (лет)"
    )
    alert_days_before = models.PositiveSmallIntegerField(
        default=30, verbose_name="Предупреждать за (дней)"
    )
    auto_purge_enabled = models.BooleanField(
        default=False, verbose_name="Разрешить авто-удаление по сроку"
    )
    last_purge_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Политика хранения данных"


class BackupRecord(models.Model):
    """M81 — запись резервного копирования."""

    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успех"
        FAILED = "failed", "Ошибка"

    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="backups")
    label = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    size_mb = models.PositiveIntegerField(default=0)
    storage_path = models.CharField(max_length=500, blank=True)
    log = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "Резервная копия"


class LicenseEntitlement(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="licenses")
    module = models.ForeignKey("ModuleCatalog", on_delete=models.CASCADE)
    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        unique_together = [("subsystem", "module")]


class SystemHealthSnapshot(models.Model):
    subsystem = models.ForeignKey(
        "Subsystem", null=True, blank=True, on_delete=models.CASCADE, related_name="health_snapshots"
    )
    metrics = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class OnboardingArticle(models.Model):
    """M84 — подсказка, тур или «что нового»."""

    class Kind(models.TextChoices):
        TOUR = "tour", "Тур"
        TIP = "tip", "Подсказка"
        CHANGELOG = "changelog", "Что нового"

    subsystem = models.ForeignKey(
        "Subsystem", null=True, blank=True, on_delete=models.CASCADE, related_name="onboarding_articles"
    )
    slug = models.SlugField(max_length=64)
    title = models.CharField(max_length=255)
    body = models.TextField()
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TIP)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "title"]
        verbose_name = "Материал обучения"


class UserDashboardLayout(models.Model):
    """M85 — пользовательская раскладка виджетов."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboard_layouts"
    )
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="dashboard_layouts")
    name = models.CharField(max_length=128, default="Мой дашборд")
    widgets = models.JSONField(default=list)
    is_default = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("user", "subsystem", "name")]
        verbose_name = "Раскладка дашборда"


class MarketplaceConnector(models.Model):
    """M86 — коннектор marketplace для M42."""

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    vendor = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    module_codes = models.JSONField(default=list, blank=True)
    is_certified = models.BooleanField(default=False)
    install_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["name"]
        verbose_name = "Коннектор marketplace"


class PlatformReleaseVersion(models.Model):
    """Версия релиза платформы «ДелаЮ» (для реестра и приёмки)."""

    version = models.CharField("Версия", max_length=32)
    released_at = models.DateField("Дата релиза")
    title = models.CharField("Заголовок", max_length=255)
    changelog = models.TextField("Изменения", blank=True)
    is_current = models.BooleanField("Текущая", default=False)

    class Meta:
        ordering = ["-released_at", "-version"]
        verbose_name = "Релиз платформы"
        verbose_name_plural = "Релизы платформы"

    def __str__(self):
        return f"{self.version} — {self.title}"


class ModuleComplianceEntry(models.Model):
    """Соответствие модуля Mxx экранам/API для экспертизы реестра."""

    module = models.OneToOneField(
        "ModuleCatalog",
        on_delete=models.CASCADE,
        related_name="compliance_entry",
        verbose_name="Модуль",
    )
    screen_paths = models.JSONField("Экраны (URL)", default=list, blank=True)
    api_paths = models.JSONField("API", default=list, blank=True)
    role_notes = models.CharField("Роли", max_length=500, blank=True)
    report_refs = models.CharField("Отчёты", max_length=500, blank=True)
    evidence_notes = models.TextField("Доказательства для экспертизы", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Соответствие модуля реестру"
        verbose_name_plural = "Журнал соответствия реестру"

    def __str__(self):
        return self.module.code


class GlossaryTerm(models.Model):
    """Единый глоссарий терминов платформы (UI и документы реестра)."""

    term = models.CharField("Термин", max_length=128, unique=True)
    definition = models.TextField("Определение")
    locale = models.CharField("Язык", max_length=8, default="ru")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "term"]
        verbose_name = "Термин глоссария"
        verbose_name_plural = "Глоссарий"

    def __str__(self):
        return self.term


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="user_favorites", null=True, blank=True
    )
    label = models.CharField(max_length=128)
    url_path = models.CharField(max_length=500)
    icon_class = models.CharField("Иконка Remix", max_length=64, default="ri-link")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Избранное"
        ordering = ["sort_order", "label"]


class SavedFilter(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_filters"
    )
    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, null=True, blank=True, related_name="saved_filters"
    )
    module_code = models.CharField(max_length=8)
    name = models.CharField(max_length=128)
    params = models.JSONField(default=dict)

    class Meta:
        ordering = ["module_code", "name"]


class ActivityEvent(models.Model):
    subsystem = models.ForeignKey("Subsystem", on_delete=models.CASCADE, related_name="activity")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    verb = models.CharField(max_length=64)
    target_repr = models.CharField(max_length=255)
    module_code = models.CharField(max_length=8, blank=True)
    link_path = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
