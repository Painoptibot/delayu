"""Топливный пропуск — доменные модели (тенант = Subsystem)."""
from django.conf import settings
from django.db import models
from django.utils import timezone


class FuelCategory(models.Model):
    """Категория получателя (I–V) с лимитом литров в сутки."""

    class Code(models.TextChoices):
        CRITICAL = "I", "Критическая"
        UTILITIES = "II", "ЖКХ и транспорт"
        ECONOMY = "III", "Экономика"
        ENTERPRISE = "IV", "Предприятия"
        CITIZEN = "V", "Население"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_categories"
    )
    code = models.CharField("Код", max_length=4, choices=Code.choices)
    name = models.CharField("Название", max_length=128)
    daily_limit_liters = models.PositiveSmallIntegerField("Лимит л/сутки", default=30)
    requires_moderation = models.BooleanField("Требует модерации", default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        verbose_name = "Категория топлива"
        verbose_name_plural = "Категории топлива"
        unique_together = [("subsystem", "code")]
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class FuelCitizen(models.Model):
    """Заявитель портала (вход по телефону)."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_citizens"
    )
    phone = models.CharField("Телефон", max_length=32, db_index=True)
    full_name = models.CharField("ФИО", max_length=255, blank=True)
    email = models.EmailField("E-mail", blank=True)
    notify_sms = models.BooleanField("Дублировать пропуск по SMS", default=False)
    notify_max = models.BooleanField("Уведомления в MAX", default=False)
    max_chat_id = models.CharField("ID чата MAX", max_length=128, blank=True, default="")
    pd_consent_at = models.DateTimeField("Согласие на обработку ПДн", null=True, blank=True)
    esia_oid = models.CharField("Идентификатор ЕСИА", max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Заявитель (топливо)"
        verbose_name_plural = "Заявители (топливо)"
        unique_together = [("subsystem", "phone")]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.full_name or self.phone}"


class FuelAzsStation(models.Model):
    """АЗС в контуре города."""

    class Status(models.TextChoices):
        OK = "ok", "Норма"
        LOW = "low", "Мало топлива"
        BUSY = "busy", "Перегрузка"
        EMPTY = "empty", "Нет бензина"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_azs_stations"
    )
    code = models.CharField("Код", max_length=32)
    name = models.CharField("Название", max_length=255)
    network = models.CharField("Сеть", max_length=128, blank=True)
    address = models.CharField("Адрес", max_length=512)
    district = models.CharField("Район", max_length=64, blank=True, default="")
    latitude = models.DecimalField(
        "Широта", max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        "Долгота", max_digits=9, decimal_places=6, null=True, blank=True
    )
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.OK
    )
    stock_liters = models.PositiveIntegerField("Остаток, л", default=0)
    queue_minutes = models.PositiveSmallIntegerField("Очередь, мин", default=0)
    is_accepting_permits = models.BooleanField("Принимает пропуска", default=True)
    fuel_grade = models.CharField("Марка", max_length=32, default="АИ-95")
    portal_login = models.CharField("Логин портала АЗС", max_length=64, blank=True)
    portal_pin = models.CharField("PIN портала АЗС", max_length=16, blank=True)
    portal_blocked = models.BooleanField("Доступ к порталу заблокирован", default=False)
    is_archived = models.BooleanField("В архиве", default=False)
    archived_at = models.DateTimeField("Дата архивации", null=True, blank=True)
    pump_count = models.PositiveSmallIntegerField("Рабочих колонок", default=2)
    avg_refuel_minutes = models.PositiveSmallIntegerField("Среднее время заправки, мин", default=8)
    use_manual_queue = models.BooleanField("Очередь вручную", default=False)
    max_apps_override = models.PositiveIntegerField(
        "Лимит заявок (ручной)", null=True, blank=True
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "АЗС"
        verbose_name_plural = "АЗС"
        unique_together = [("subsystem", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class FuelApplication(models.Model):
    """Заявка на топливный пропуск."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        PENDING = "pending", "На проверке"
        APPROVED = "approved", "Одобрено"
        REJECTED = "rejected", "Отклонено"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_applications"
    )
    citizen = models.ForeignKey(
        FuelCitizen, on_delete=models.CASCADE, related_name="applications"
    )
    number = models.CharField("Номер", max_length=32, db_index=True)
    category = models.ForeignKey(
        FuelCategory, on_delete=models.PROTECT, related_name="applications"
    )
    plate = models.CharField("Госномер", max_length=16, db_index=True)
    vehicle_make = models.CharField("Марка ТС", max_length=128, blank=True)
    inn = models.CharField("ИНН", max_length=12, blank=True)
    org_name = models.CharField("Организация", max_length=255, blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    assigned_azs = models.ForeignKey(
        FuelAzsStation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_applications",
    )
    reject_reason = models.TextField("Причина отказа", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Заявка на пропуск"
        verbose_name_plural = "Заявки на пропуск"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number


class FuelPermit(models.Model):
    """Выданный QR-пропуск."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Действует"
        REVOKED = "revoked", "Отозван"
        EXPIRED = "expired", "Истёк"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_permits"
    )
    application = models.OneToOneField(
        FuelApplication, on_delete=models.CASCADE, related_name="permit"
    )
    number = models.CharField("Номер", max_length=32, unique=True)
    plate = models.CharField("Госномер", max_length=16, db_index=True)
    category = models.ForeignKey(FuelCategory, on_delete=models.PROTECT)
    max_liters = models.PositiveSmallIntegerField("Лимит, л")
    remaining_liters = models.PositiveSmallIntegerField("Остаток, л")
    assigned_azs = models.ForeignKey(
        FuelAzsStation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="permits",
    )
    valid_until = models.DateTimeField("Действует до")
    manual_code = models.CharField("Код для ручного ввода", max_length=8, blank=True)
    qr_payload = models.TextField("Payload QR", blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Топливный пропуск"
        verbose_name_plural = "Топливные пропуска"
        ordering = ["-created_at"]

    def __str__(self):
        return self.number

    @property
    def is_valid_now(self) -> bool:
        return (
            self.status == self.Status.ACTIVE
            and self.remaining_liters > 0
            and self.valid_until >= timezone.now()
        )


class FuelRedeem(models.Model):
    """Факт отпуска на АЗС."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_redeems"
    )
    permit = models.ForeignKey(FuelPermit, on_delete=models.CASCADE, related_name="redeems")
    azs = models.ForeignKey(FuelAzsStation, on_delete=models.PROTECT, related_name="redeems")
    plate = models.CharField("Госномер", max_length=16)
    liters = models.DecimalField("Литры", max_digits=6, decimal_places=2)
    operator_note = models.CharField("Примечание", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Отпуск топлива"
        verbose_name_plural = "Отпуски топлива"
        ordering = ["-created_at"]


class FuelRedeemAttempt(models.Model):
    """Журнал попыток отпуска (успех / отказ) для аналитики."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_redeem_attempts"
    )
    azs = models.ForeignKey(
        FuelAzsStation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="redeem_attempts",
    )
    plate = models.CharField("Госномер", max_length=16, blank=True)
    success = models.BooleanField(default=False)
    error_code = models.CharField("Код ошибки", max_length=32, blank=True)
    liters = models.DecimalField("Литры", max_digits=6, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Попытка отпуска"
        verbose_name_plural = "Попытки отпуска"
        ordering = ["-created_at"]


class FuelBlacklistEntry(models.Model):
    """Чёрный список ГРЗ / ИНН."""

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_blacklist"
    )
    plate = models.CharField("Госномер", max_length=16, blank=True, db_index=True)
    inn = models.CharField("ИНН", max_length=12, blank=True, db_index=True)
    reason = models.CharField("Причина", max_length=255)
    is_active = models.BooleanField(default=True)
    deactivated_at = models.DateTimeField("Снято с ограничения", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Чёрный список (топливо)"
        verbose_name_plural = "Чёрный список (топливо)"


class FuelEventLog(models.Model):
    """Журнал действий операторов, АЗС и портала жителя."""

    class Channel(models.TextChoices):
        OPERATOR = "operator", "Оператор штаба"
        AZS = "azs", "Портал АЗС"
        CITIZEN = "citizen", "Портал жителя"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_event_logs"
    )
    channel = models.CharField("Контур", max_length=16, choices=Channel.choices, db_index=True)
    action = models.CharField("Действие", max_length=64, db_index=True)
    summary = models.CharField("Описание", max_length=512)
    actor_label = models.CharField("Инициатор", max_length=255, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fuel_event_logs",
    )
    azs = models.ForeignKey(
        FuelAzsStation,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_logs",
    )
    citizen = models.ForeignKey(
        FuelCitizen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="event_logs",
    )
    object_type = models.CharField("Тип объекта", max_length=64, blank=True)
    object_id = models.CharField("ID объекта", max_length=64, blank=True)
    payload = models.JSONField("Данные", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Событие (топливо)"
        verbose_name_plural = "Журнал событий (топливо)"
        ordering = ["-created_at"]


class FuelParityRule(models.Model):
    """Ограничение чётности госномеров и текст уведомления для портала."""

    class Mode(models.TextChoices):
        CALENDAR = "calendar", "По календарю (день месяца)"
        EVEN = "even", "Только чётные"
        ODD = "odd", "Только нечётные"

    subsystem = models.OneToOneField(
        "Subsystem",
        on_delete=models.CASCADE,
        related_name="fuel_parity_rule",
    )
    is_enabled = models.BooleanField("Ограничение активно", default=True)
    mode = models.CharField(
        "Режим",
        max_length=16,
        choices=Mode.choices,
        default=Mode.CALENDAR,
    )
    message = models.TextField(
        "Текст уведомления",
        blank=True,
        help_text="Пусто — сформировать автоматически по режиму и дате.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Правило чётности госномеров"
        verbose_name_plural = "Правила чётности госномеров"

    def __str__(self):
        return f"Чётность · {self.subsystem}"


class FuelPortalSettings(models.Model):
    """Настройки прогноза загрузки и квот портала."""

    subsystem = models.OneToOneField(
        "Subsystem",
        on_delete=models.CASCADE,
        related_name="fuel_portal_settings",
    )
    permit_quota_liters = models.PositiveSmallIntegerField(
        "Квота заявки, л",
        default=30,
        help_text="Максимум литров в одной заявке для расчёта ёмкости АЗС",
    )
    auto_queue_enabled = models.BooleanField("Авторасчёт очереди", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки портала (топливо)"
        verbose_name_plural = "Настройки портала (топливо)"

    def __str__(self):
        return f"Настройки · {self.subsystem}"


class FuelSupportTicket(models.Model):
    """Обращение жителя в техподдержку."""

    class Status(models.TextChoices):
        NEW = "new", "Новое"
        IN_PROGRESS = "in_progress", "В работе"
        ANSWERED = "answered", "Отвечено"
        CLOSED = "closed", "Закрыто"

    subsystem = models.ForeignKey(
        "Subsystem", on_delete=models.CASCADE, related_name="fuel_support_tickets"
    )
    citizen = models.ForeignKey(
        FuelCitizen,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="support_tickets",
    )
    name = models.CharField("Имя", max_length=255)
    contact = models.CharField("Контакт", max_length=255)
    question = models.TextField("Вопрос")
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.NEW
    )
    operator_note = models.TextField("Ответ оператора", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Обращение в ТП"
        verbose_name_plural = "Обращения в ТП"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name}: {self.question[:40]}"
