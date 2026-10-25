"""Сервисный контур: карточка заказчика, каналы и полевой учёт объектов."""
from decimal import Decimal

from django.conf import settings
from django.db import models


class ServiceCustomer(models.Model):
    class Stage(models.TextChoices):
        """Воронка LED SALES, как в аккаунте Canadian LED."""

        NEW_LEAD = "new_lead", "New Lead"
        CONTACTED = "contacted", "Contacted"
        REPLIED = "replied", "Replied"
        QUALIFIED = "qualified", "Qualified"
        MEETING = "meeting", "Meeting scheduled"
        PROPOSAL = "proposal", "Proposal Sent"
        ACTIVE = "active", "Active Deal"
        INVOICE = "invoice", "Invoice Sent"
        SETUP = "setup", "Equipment Setup"
        WON = "won", "Won"

    class JobType(models.TextChoices):
        SALE = "sale", "Продажа экрана"
        RENTAL = "rental", "Аренда на событие"
        STREAMING = "streaming", "Трансляция"
        STAGE = "stage", "Сцена"
        TRUSS = "truss", "Фермы"

    class Placement(models.TextChoices):
        INDOOR = "indoor", "Indoor"
        OUTDOOR = "outdoor", "Outdoor"
        MOBILE = "mobile", "Mobile"

    class PaymentState(models.TextChoices):
        NONE = "none", "Нет счёта"
        INVOICED = "invoiced", "Счёт выставлен"
        PARTIAL = "partial", "Частично оплачено"
        PAID = "paid", "Оплачено"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_customers"
    )
    number = models.CharField("Номер", max_length=32, db_index=True)
    display_name = models.CharField("Заказчик", max_length=255)
    company = models.CharField("Организация", max_length=255, blank=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    email = models.EmailField("Почта", blank=True)
    address = models.CharField("Адрес", max_length=512, blank=True)
    city = models.CharField("Город", max_length=128, blank=True)
    state = models.CharField("Штат", max_length=32, blank=True)
    stage = models.CharField(
        "Стадия воронки", max_length=16, choices=Stage.choices, default=Stage.NEW_LEAD
    )
    payment_state = models.CharField(
        "Оплата",
        max_length=16,
        choices=PaymentState.choices,
        default=PaymentState.NONE,
    )
    invoice_amount = models.DecimalField(
        "Сумма счёта", max_digits=12, decimal_places=2, null=True, blank=True
    )
    tags = models.CharField("Метки", max_length=255, blank=True)
    notes = models.TextField("Заметки", blank=True)
    attributes = models.JSONField("Дополнительные атрибуты", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Заказчик сервисного контура"
        verbose_name_plural = "Заказчики сервисного контура"
        ordering = ["-updated_at"]
        unique_together = [("subsystem", "number")]

    def __str__(self):
        return f"{self.number} — {self.display_name}"


class ServiceChannel(models.Model):
    class Status(models.TextChoices):
        READY = "ready", "Принимает в карточку"
        PAUSED = "paused", "На паузе"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_channels"
    )
    code = models.CharField("Код", max_length=32)
    title = models.CharField("Канал", max_length=64)
    detail = models.CharField("Как попадает в карточку", max_length=255)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.READY
    )

    class Meta:
        verbose_name = "Канал диалога"
        verbose_name_plural = "Каналы диалога"
        ordering = ["title"]
        unique_together = [("subsystem", "code")]

    def __str__(self):
        return self.title


class ServiceDeal(models.Model):
    """Сделка в воронке. У одного заказчика их может быть несколько."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        WON = "won", "Won"
        LOST = "lost", "Lost"

    class Answer(models.TextChoices):
        UNKNOWN = "unknown", "Не выяснено"
        YES = "yes", "Да"
        NO = "no", "Нет"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_deals"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="deals"
    )
    number = models.CharField("Номер", max_length=32)
    title = models.CharField("Сделка", max_length=255)
    stage = models.CharField(
        "Стадия",
        max_length=16,
        choices=ServiceCustomer.Stage.choices,
        default=ServiceCustomer.Stage.NEW_LEAD,
    )
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.OPEN
    )
    job_type = models.CharField(
        "Задача",
        max_length=16,
        choices=ServiceCustomer.JobType.choices,
        default=ServiceCustomer.JobType.SALE,
    )
    source = models.CharField("Источник", max_length=128, blank=True)
    city = models.CharField("Город", max_length=128, blank=True)
    state = models.CharField("Провинция", max_length=32, blank=True)
    venue = models.CharField("Площадка", max_length=255, blank=True)
    placement = models.CharField(
        "Где экран",
        max_length=16,
        choices=ServiceCustomer.Placement.choices,
        default=ServiceCustomer.Placement.INDOOR,
    )
    width_ft = models.DecimalField(
        "Ширина, ft", max_digits=6, decimal_places=1, null=True, blank=True
    )
    height_ft = models.DecimalField(
        "Высота, ft", max_digits=6, decimal_places=1, null=True, blank=True
    )
    timeline = models.CharField("Срок проекта", max_length=255, blank=True)
    event_on = models.DateField("Дата события", null=True, blank=True)
    value = models.DecimalField(
        "Сумма, C$", max_digits=12, decimal_places=2, null=True, blank=True
    )
    decision_maker = models.CharField(
        "Кто принимает решение",
        max_length=16,
        choices=Answer.choices,
        default=Answer.UNKNOWN,
    )
    screen_over_30 = models.CharField(
        "Экран больше 30 кв. футов",
        max_length=16,
        choices=Answer.choices,
        default=Answer.UNKNOWN,
    )
    guests_over_200 = models.CharField(
        "Гостей больше 200",
        max_length=16,
        choices=Answer.choices,
        default=Answer.UNKNOWN,
    )
    church_project = models.CharField(
        "Церковный проект",
        max_length=16,
        choices=Answer.choices,
        default=Answer.UNKNOWN,
    )
    qualification = models.CharField("Квалификация", max_length=255, blank=True)
    lost_reason = models.CharField("Причина проигрыша", max_length=255, blank=True)
    owner_name = models.CharField("Владелец", max_length=128, blank=True)
    observers = models.CharField("Наблюдатели", max_length=255, blank=True)
    paused = models.BooleanField("Пауза дела", default=False)
    pause_reason = models.CharField("Причина паузы", max_length=255, blank=True)
    next_on = models.DateField("Следующее действие", null=True, blank=True)
    warranty_on = models.DateField("Гарантия до", null=True, blank=True)
    revision = models.PositiveIntegerField("Редакция", default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Сделка LED SALES"
        verbose_name_plural = "Сделки LED SALES"
        ordering = ["-updated_at"]
        unique_together = [("subsystem", "number")]

    def __str__(self):
        return f"{self.number} — {self.title}"


class ServiceObject(models.Model):
    class WorkStage(models.TextChoices):
        PROPOSAL = "proposal", "Предложение"
        SETUP = "setup", "Монтаж"
        COMPLETE = "complete", "Завершено"

    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирован"
        ACTIVE = "active", "В работе"
        PAUSED = "paused", "Пауза"
        DONE = "done", "Завершён"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_objects"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.PROTECT, related_name="sites"
    )
    code = models.CharField("Код", max_length=32)
    title = models.CharField("Площадка", max_length=255)
    address = models.CharField("Адрес", max_length=512, blank=True)
    city = models.CharField("Город", max_length=128, blank=True)
    state = models.CharField("Штат", max_length=32, blank=True)
    job_type = models.CharField(
        "Задача",
        max_length=16,
        choices=ServiceCustomer.JobType.choices,
        default=ServiceCustomer.JobType.RENTAL,
    )
    placement = models.CharField(
        "Где экран",
        max_length=16,
        choices=ServiceCustomer.Placement.choices,
        default=ServiceCustomer.Placement.INDOOR,
    )
    width_ft = models.DecimalField(
        "Ширина, ft", max_digits=6, decimal_places=1, null=True, blank=True
    )
    height_ft = models.DecimalField(
        "Высота, ft", max_digits=6, decimal_places=1, null=True, blank=True
    )
    event_on = models.DateField("Дата события или монтажа", null=True, blank=True)
    stage = models.CharField(
        "Этап работ",
        max_length=16,
        choices=WorkStage.choices,
        default=WorkStage.PROPOSAL,
    )
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.PLANNED
    )
    notes = models.TextField("Заметки", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Объект"
        verbose_name_plural = "Объекты"
        ordering = ["title"]
        unique_together = [("subsystem", "code")]

    def __str__(self):
        return f"{self.code} — {self.title}"


class ServiceMessage(models.Model):
    class Direction(models.TextChoices):
        IN = "in", "Входящее"
        OUT = "out", "Исходящее"

    class AuthorKind(models.TextChoices):
        CUSTOMER = "customer", "Заказчик"
        STAFF = "staff", "Сотрудник"
        AGENT = "agent", "ИИ-агент"

    class Kind(models.TextChoices):
        DIALOGUE = "dialogue", "Диалог"
        ANSWER = "answer", "Ответ агента"
        STAGE = "stage", "Этап работ"
        PAYMENT = "payment", "Оплата"

    class Status(models.TextChoices):
        SCHEDULED = "scheduled", "Ждёт срока"
        SENT = "sent", "В карточке"

    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="messages"
    )
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_messages"
    )
    channel = models.CharField("Канал", max_length=32)
    direction = models.CharField("Направление", max_length=8, choices=Direction.choices)
    author_kind = models.CharField("Автор", max_length=16, choices=AuthorKind.choices)
    kind = models.CharField("Вид", max_length=16, choices=Kind.choices, default=Kind.DIALOGUE)
    body = models.TextField("Текст")
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.SENT
    )
    scheduled_for = models.DateTimeField("Срок отправки", null=True, blank=True)
    sent_at = models.DateTimeField("Попало в карточку", null=True, blank=True)
    last_error = models.CharField("Почему не ушло", max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_messages",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Сообщение карточки"
        verbose_name_plural = "Сообщения карточки"
        ordering = ["created_at", "pk"]

    def __str__(self):
        return f"{self.get_direction_display()} {self.channel}"

    @property
    def channel_label(self) -> str:
        from delayu.services.service_channels import channel_title

        row = ServiceChannel.objects.filter(subsystem_id=self.subsystem_id, code=self.channel).first()
        if row is not None:
            return row.title
        return channel_title(self.channel)


class ServiceVisit(models.Model):
    """Выезд сотрудника на объект: дорога, время и прочие издержки."""

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_visits"
    )
    site = models.ForeignKey(ServiceObject, on_delete=models.CASCADE, related_name="visits")
    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_visits"
    )
    departed_on = models.DateField("Дата выезда")
    distance_mi = models.DecimalField("Мили", max_digits=8, decimal_places=2, default=0)
    rate_per_mile = models.DecimalField("Ставка за милю", max_digits=10, decimal_places=2, default=0)
    hours = models.DecimalField("Часы на объекте", max_digits=8, decimal_places=2, default=0)
    hour_rate = models.DecimalField("Ставка часа", max_digits=10, decimal_places=2, default=0)
    other_cost = models.DecimalField("Прочие издержки", max_digits=12, decimal_places=2, default=0)
    travel_cost = models.DecimalField("Дорога", max_digits=12, decimal_places=2, default=0)
    labor_cost = models.DecimalField("Работа", max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField("Итого выезд", max_digits=12, decimal_places=2, default=0)
    note = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        verbose_name = "Выезд"
        verbose_name_plural = "Выезды"
        ordering = ["-departed_on", "-pk"]

    def save(self, *args, **kwargs):
        from delayu.services.service_field import apply_visit_costs

        apply_visit_costs(self)
        super().save(*args, **kwargs)


class ServiceDeployment(models.Model):
    """Силы и средства, списанные на объект."""

    class Kind(models.TextChoices):
        PEOPLE = "people", "Люди"
        VEHICLE = "vehicle", "Транспорт"
        EQUIPMENT = "equipment", "Техника"
        MATERIAL = "material", "Материалы"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_deployments"
    )
    site = models.ForeignKey(
        ServiceObject, on_delete=models.CASCADE, related_name="deployments"
    )
    kind = models.CharField("Вид", max_length=16, choices=Kind.choices)
    title = models.CharField("Наименование", max_length=255)
    quantity = models.DecimalField("Количество", max_digits=10, decimal_places=2)
    unit = models.CharField("Единица", max_length=32, default="шт")
    unit_cost = models.DecimalField("Цена единицы", max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField("Сумма", max_digits=12, decimal_places=2, default=0)
    note = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        verbose_name = "Силы и средства"
        verbose_name_plural = "Силы и средства"
        ordering = ["kind", "title"]

    def save(self, *args, **kwargs):
        from delayu.services.service_field import apply_deployment_costs

        apply_deployment_costs(self)
        super().save(*args, **kwargs)


class ServiceCalendar(models.Model):
    class Kind(models.TextChoices):
        MEETING = "meeting", "Встреча"
        RENTAL = "rental", "Аренда"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_calendars"
    )
    name = models.CharField("Календарь", max_length=255)
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.MEETING)
    minutes = models.PositiveIntegerField("Минут", default=30)
    owner_name = models.CharField("Ведущий", max_length=128, blank=True)
    active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Календарь"
        verbose_name_plural = "Календари"
        ordering = ["kind", "name"]
        unique_together = [("subsystem", "name")]

    def __str__(self):
        return self.name


class ServiceAppointment(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_appointments"
    )
    calendar = models.ForeignKey(
        ServiceCalendar, on_delete=models.PROTECT, related_name="appointments"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="appointments"
    )
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="appointments"
    )
    starts_at = models.DateTimeField("Начало")
    minutes = models.PositiveIntegerField("Минут", default=30)
    note = models.CharField("Заметка", max_length=255, blank=True)

    class Meta:
        verbose_name = "Встреча"
        verbose_name_plural = "Встречи"
        ordering = ["starts_at"]


class ServiceWorkflow(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "published", "Опубликован"
        DRAFT = "draft", "Черновик"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_workflows"
    )
    code = models.CharField("Код", max_length=64)
    folder = models.CharField("Папка", max_length=128)
    name = models.CharField("Сценарий", max_length=255)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.PUBLISHED
    )
    trigger = models.CharField("Событие", max_length=32)
    action = models.CharField("Действие", max_length=32)
    enrolled = models.PositiveIntegerField("Прошли", default=0)

    class Meta:
        verbose_name = "Сценарий"
        verbose_name_plural = "Сценарии"
        ordering = ["folder", "name"]
        unique_together = [("subsystem", "code")]


class ServiceFunnel(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        DRAFT = "draft", "Черновик"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_funnels"
    )
    name = models.CharField("Воронка", max_length=255)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )
    steps = models.TextField("Шаги", blank=True)

    class Meta:
        verbose_name = "Воронка сайта"
        verbose_name_plural = "Воронки сайта"
        ordering = ["name"]
        unique_together = [("subsystem", "name")]


class ServiceMailing(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_mailings"
    )
    subject = models.CharField("Тема", max_length=255)
    body = models.TextField("Письмо")
    audience = models.CharField("Метка аудитории", max_length=64, blank=True)
    sent_count = models.PositiveIntegerField("Отправлено", default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"
        ordering = ["-created_at"]


class ServiceAd(models.Model):
    class Network(models.TextChoices):
        GOOGLE = "Google", "Google"
        META = "Meta", "Meta"
        BING = "Bing", "Bing"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_ads"
    )
    name = models.CharField("Кампания", max_length=255)
    network = models.CharField("Сеть", max_length=16, choices=Network.choices)
    province = models.CharField("Провинция", max_length=8, blank=True)
    job_type = models.CharField(
        "Задача",
        max_length=16,
        choices=ServiceCustomer.JobType.choices,
        default=ServiceCustomer.JobType.SALE,
    )
    active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Реклама"
        verbose_name_plural = "Реклама"
        ordering = ["network", "name"]


class ServiceInvoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SENT = "sent", "Отправлен"
        PAID = "paid", "Оплачен"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_invoices"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.PROTECT, related_name="invoices"
    )
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    number = models.CharField("Номер", max_length=32)
    title = models.CharField("Счёт", max_length=255)
    amount = models.DecimalField("Сумма, C$", max_digits=12, decimal_places=2)
    kind = models.CharField(
        "Вид платежа",
        max_length=16,
        choices=[("deposit", "Задаток"), ("final", "Остаток")],
        default="final",
    )
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    issued_on = models.DateField("Дата")

    class Meta:
        verbose_name = "Счёт"
        verbose_name_plural = "Счета"
        ordering = ["-issued_on", "-pk"]
        unique_together = [("subsystem", "number")]


class ServiceField(models.Model):
    """Своё поле контакта, сделки или компании. Значения заказчиков сюда не копируются."""

    class Record(models.TextChoices):
        CONTACT = "contact", "Контакт"
        OPPORTUNITY = "opportunity", "Сделка"
        COMPANY = "company", "Компания"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_fields"
    )
    folder = models.CharField("Папка", max_length=128, blank=True)
    name = models.CharField("Поле", max_length=255)
    field_type = models.CharField("Тип", max_length=64)
    record = models.CharField(
        "Карточка", max_length=16, choices=Record.choices, default=Record.CONTACT
    )
    key = models.CharField("Ключ", max_length=180)

    class Meta:
        verbose_name = "Своё поле"
        verbose_name_plural = "Свои поля"
        ordering = ["folder", "name"]
        unique_together = [("subsystem", "key")]


class ServiceForm(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Активна"
        DRAFT = "draft", "Черновик"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_forms"
    )
    folder = models.CharField("Папка", max_length=128, blank=True)
    name = models.CharField("Форма", max_length=255)
    prompt = models.TextField("Что спрашивает", blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.ACTIVE
    )

    class Meta:
        verbose_name = "Форма"
        verbose_name_plural = "Формы"
        ordering = ["folder", "name"]
        unique_together = [("subsystem", "name")]


class ServicePhone(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_phones"
    )
    number = models.CharField("Номер", max_length=32)
    title = models.CharField("Имя", max_length=128)
    forward_to = models.CharField("Переадресация", max_length=32, blank=True)
    timeout_seconds = models.PositiveIntegerField("Таймаут, с", default=60)

    class Meta:
        verbose_name = "Номер"
        verbose_name_plural = "Номера"
        ordering = ["title"]
        unique_together = [("subsystem", "number")]


class ServiceStaff(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_staff"
    )
    name = models.CharField("Имя", max_length=255)
    email = models.EmailField("Почта")
    role_name = models.CharField("Роль", max_length=64)

    class Meta:
        verbose_name = "Сотрудник локации"
        verbose_name_plural = "Сотрудники локации"
        ordering = ["name"]
        unique_together = [("subsystem", "email")]


class ServiceMedia(models.Model):
    class Kind(models.TextChoices):
        IMAGE = "image", "Изображение"
        VIDEO = "video", "Видео"
        FILE = "file", "Файл"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_media"
    )
    folder = models.CharField("Папка", max_length=128, blank=True)
    title = models.CharField("Файл", max_length=255)
    kind = models.CharField("Тип", max_length=16, choices=Kind.choices, default=Kind.IMAGE)
    file = models.FileField("Файл", upload_to="service-media/", blank=True)
    note = models.CharField("Заметка", max_length=255, blank=True)
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="media_files"
    )
    job_type = models.CharField("Тип работ", max_length=16, blank=True)

    class Meta:
        verbose_name = "Медиа"
        verbose_name_plural = "Медиатека"
        ordering = ["folder", "title"]


class ServiceTask(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_tasks"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="tasks"
    )
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="tasks"
    )
    class Kind(models.TextChoices):
        CALL = "call", "Звонок"
        EMAIL = "email", "Письмо"
        VISIT = "visit", "Выезд"
        SETUP = "setup", "Монтаж"
        FOLLOWUP = "followup", "Дожим"

    title = models.CharField("Задача", max_length=255)
    kind = models.CharField(
        "Шаг", max_length=16, choices=Kind.choices, default=Kind.CALL
    )
    due_on = models.DateField("Срок", null=True, blank=True)
    done = models.BooleanField("Сделано", default=False)
    note = models.CharField("Заметка", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Задача"
        verbose_name_plural = "Задачи"
        ordering = ["done", "due_on", "-pk"]


class ServiceJobType(models.Model):
    """Справочник видов работ. Новый вид не заводит отдельные экраны."""

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_job_types"
    )
    code = models.CharField("Код", max_length=16)
    title = models.CharField("Вид работ", max_length=128)
    active = models.BooleanField("В работе", default=True)

    class Meta:
        verbose_name = "Вид работ"
        verbose_name_plural = "Виды работ"
        ordering = ["title"]
        unique_together = [("subsystem", "code")]

    def __str__(self):
        return self.title


class ServicePlaybook(models.Model):
    """Правила одного вида работ: стадии, тексты, SLA и нормы."""

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_playbooks"
    )
    job_type = models.CharField("Вид работ", max_length=16)
    name = models.CharField("Плейбук", max_length=128)
    sla_first_hours = models.PositiveIntegerField("Часы на первое касание", default=1)
    sla_stage_hours = models.PositiveIntegerField("Часы на стадию", default=24)
    mile_rate = models.DecimalField("Норма мили, C$", max_digits=10, decimal_places=2, default=0)
    hour_rate = models.DecimalField("Норма часа, C$", max_digits=10, decimal_places=2, default=0)
    crew_rate = models.DecimalField("Норма единицы силы, C$", max_digits=10, decimal_places=2, default=0)
    meeting_advances = models.BooleanField("Встреча двигает стадию", default=True)
    gates = models.JSONField("Правила стадий", default=dict, blank=True)
    messages = models.JSONField("Тексты стадий", default=dict, blank=True)
    steps = models.TextField("Шаги дожима", blank=True)
    stale_days = models.PositiveIntegerField("Дней без движения", default=7)
    warranty_days = models.PositiveIntegerField("Дней гарантии", default=0)
    approval_amount = models.DecimalField(
        "Порог согласования, C$", max_digits=12, decimal_places=2, default=0
    )
    after_hours = models.CharField("Текст вне часов", max_length=255, blank=True)

    class Meta:
        verbose_name = "Плейбук"
        verbose_name_plural = "Плейбуки"
        ordering = ["name"]
        unique_together = [("subsystem", "job_type")]

    def __str__(self):
        return self.name


class ServiceContact(models.Model):
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="contacts"
    )
    name = models.CharField("Имя", max_length=255)
    role_name = models.CharField("Роль", max_length=128, blank=True)
    phone = models.CharField("Телефон", max_length=32, blank=True)
    email = models.EmailField("Почта", blank=True)
    decides = models.BooleanField("Принимает решение", default=False)

    class Meta:
        verbose_name = "Контакт"
        verbose_name_plural = "Контакты"
        ordering = ["-decides", "name"]

    def __str__(self):
        return self.name


class ServiceReason(models.Model):
    class Kind(models.TextChoices):
        LOST = "lost", "Проигрыш"
        PAUSE = "pause", "Пауза"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_reasons"
    )
    kind = models.CharField("Вид", max_length=16, choices=Kind.choices)
    title = models.CharField("Причина", max_length=128)

    class Meta:
        verbose_name = "Причина"
        verbose_name_plural = "Причины"
        ordering = ["kind", "title"]
        unique_together = [("subsystem", "kind", "title")]

    def __str__(self):
        return self.title


class ServiceAudit(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_audits"
    )
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="audits"
    )
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="audits"
    )
    actor = models.CharField("Кто", max_length=128)
    action = models.CharField("Что", max_length=64)
    detail = models.CharField("Как было", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "След решения"
        verbose_name_plural = "След решений"
        ordering = ["-created_at", "-pk"]


class ServiceCrewLine(models.Model):
    class Kind(models.TextChoices):
        PEOPLE = "people", "Люди"
        GEAR = "gear", "Техника"

    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_crew_lines"
    )
    deal = models.ForeignKey(ServiceDeal, on_delete=models.CASCADE, related_name="crew_lines")
    site = models.ForeignKey(
        ServiceObject, null=True, blank=True, on_delete=models.SET_NULL, related_name="crew_lines"
    )
    title = models.CharField("Сила", max_length=128)
    kind = models.CharField("Вид", max_length=16, choices=Kind.choices, default=Kind.PEOPLE)
    planned = models.DecimalField("План", max_digits=8, decimal_places=1, default=0)
    actual = models.DecimalField("Факт", max_digits=8, decimal_places=1, default=0)
    unit = models.CharField("Единица", max_length=32, default="чел")
    damaged = models.BooleanField("Повреждение", default=False)

    class Meta:
        verbose_name = "План сил"
        verbose_name_plural = "План сил"
        ordering = ["kind", "title"]


class ServiceObjectDeal(models.Model):
    """Площадка живёт отдельно и может обслуживать несколько дел."""

    site = models.ForeignKey(ServiceObject, on_delete=models.CASCADE, related_name="deal_links")
    deal = models.ForeignKey(ServiceDeal, on_delete=models.CASCADE, related_name="site_links")

    class Meta:
        verbose_name = "Площадка дела"
        verbose_name_plural = "Площадки дел"
        unique_together = [("site", "deal")]


class ServiceChecklist(models.Model):
    playbook = models.ForeignKey(
        ServicePlaybook, on_delete=models.CASCADE, related_name="checks"
    )
    stage = models.CharField("Стадия", max_length=16)
    title = models.CharField("Пункт", max_length=255)

    class Meta:
        verbose_name = "Пункт плейбука"
        verbose_name_plural = "Пункты плейбука"
        unique_together = [("playbook", "stage", "title")]
        ordering = ["stage", "title"]


class ServiceCheckMark(models.Model):
    deal = models.ForeignKey(ServiceDeal, on_delete=models.CASCADE, related_name="check_marks")
    item = models.ForeignKey(ServiceChecklist, on_delete=models.CASCADE, related_name="marks")
    done = models.BooleanField("Сделано", default=False)

    class Meta:
        unique_together = [("deal", "item")]


class ServiceNote(models.Model):
    customer = models.ForeignKey(
        ServiceCustomer, on_delete=models.CASCADE, related_name="internal_notes"
    )
    deal = models.ForeignKey(
        ServiceDeal, null=True, blank=True, on_delete=models.SET_NULL, related_name="internal_notes"
    )
    body = models.CharField("Заметка сотруднику", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class ServiceRoute(models.Model):
    subsystem = models.ForeignKey(
        "delayu.Subsystem", on_delete=models.CASCADE, related_name="service_routes"
    )
    job_type = models.CharField("Вид работ", max_length=16)
    province = models.CharField("Провинция", max_length=8)
    owner_name = models.CharField("Владелец", max_length=128)

    class Meta:
        unique_together = [("subsystem", "job_type", "province")]
        ordering = ["province", "job_type"]


class ServiceGear(models.Model):
    site = models.ForeignKey(ServiceObject, on_delete=models.CASCADE, related_name="gears")
    title = models.CharField("Оборудование", max_length=128)
    serial = models.CharField("Серийный номер", max_length=64)

    class Meta:
        unique_together = [("site", "serial")]
        ordering = ["title"]


def money(value) -> Decimal:
    return Decimal(value or 0).quantize(Decimal("0.01"))
