from django.conf import settings
from django.db import models


class ModuleCatalog(models.Model):
    """Каталог функциональных модулей M01–M86."""

    class Group(models.TextChoices):
        CORE = "core", "Ядро"
        WORKPLACE = "workplace", "Рабочее место"
        ANALYTICS = "analytics", "Аналитика"
        CASES = "cases", "Дела и реестры"
        DOCS = "docs", "Документооборот"
        BPM = "bpm", "Бизнес-процессы"
        COMMS = "comms", "Коммуникации"
        INTEGRATION = "integration", "Интеграции"
        ARCHIVE = "archive", "Архив"
        AI = "ai", "ИИ"
        INFRA = "infra", "Инфраструктура"
        NSI = "nsi", "НСИ и операции"
        OPS = "ops", "Эксплуатация"
        UX = "ux", "UX и лицензии"

    code = models.CharField("Код", max_length=8, unique=True, db_index=True)
    name = models.CharField("Наименование", max_length=255)
    description = models.TextField("Описание", blank=True)
    group = models.CharField("Группа", max_length=32, choices=Group.choices, default=Group.CORE)
    is_core = models.BooleanField("Ядро", default=False)
    sort_order = models.PositiveSmallIntegerField("Порядок", default=0)
    is_active = models.BooleanField("В каталоге", default=True)

    class Meta:
        verbose_name = "Модуль каталога"
        verbose_name_plural = "Каталог модулей"
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Subsystem(models.Model):
    """Конфигурация платформы для контура заказчика (M01)."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        ACTIVE = "active", "Действует"
        ARCHIVED = "archived", "Архив"

    code = models.SlugField("Код", max_length=64, unique=True)
    name = models.CharField("Наименование", max_length=255)
    description = models.TextField("Описание", blank=True)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    primary_color = models.CharField("Цвет бренда", max_length=16, blank=True, default="#666cff")
    industry_template = models.CharField(
        "Шаблон отрасли",
        max_length=32,
        default="generic",
        choices=[
            ("generic", "Универсальная"),
            ("municipal", "Муниципалитет"),
            ("agency", "Ведомство"),
            ("holding", "Холдинг"),
            ("uzhv", "АИС УЖВ"),
        ],
    )
    config_version = models.CharField("Версия конфигурации", max_length=32, blank=True)
    menu_layout = models.JSONField("Меню (конструктор)", default=list, blank=True)
    correspondence_workflow = models.JSONField("Маршрут СЭД", default=dict, blank=True)
    published_at = models.DateTimeField("Опубликовано", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Подсистема"
        verbose_name_plural = "Подсистемы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SubsystemModule(models.Model):
    """Матрица: модуль включён в подсистему."""

    subsystem = models.ForeignKey(
        Subsystem, on_delete=models.CASCADE, related_name="module_links"
    )
    module = models.ForeignKey(
        ModuleCatalog, on_delete=models.CASCADE, related_name="subsystem_links"
    )
    enabled = models.BooleanField("Включён", default=True)

    class Meta:
        verbose_name = "Модуль подсистемы"
        verbose_name_plural = "Модули подсистемы"
        unique_together = [("subsystem", "module")]

    def __str__(self):
        return f"{self.subsystem.code}: {self.module.code}"


class Organization(models.Model):
    """Организация в контуре подсистемы."""

    subsystem = models.ForeignKey(
        Subsystem, on_delete=models.CASCADE, related_name="organizations"
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
    )
    code = models.CharField("Код", max_length=64)
    name = models.CharField("Наименование", max_length=255)
    is_active = models.BooleanField("Активна", default=True)

    class Meta:
        verbose_name = "Организация"
        verbose_name_plural = "Организации"
        unique_together = [("subsystem", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Role(models.Model):
    """Роль в подсистеме (M02)."""

    subsystem = models.ForeignKey(Subsystem, on_delete=models.CASCADE, related_name="roles")
    code = models.CharField("Код", max_length=64)
    name = models.CharField("Наименование", max_length=128)
    description = models.TextField("Описание", blank=True)
    is_system = models.BooleanField("Системная", default=False)

    class Meta:
        verbose_name = "Роль"
        verbose_name_plural = "Роли"
        unique_together = [("subsystem", "code")]
        ordering = ["name"]

    def __str__(self):
        return self.name


class RoleModulePermission(models.Model):
    """Матрица: роль × модуль."""

    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="module_permissions")
    module = models.ForeignKey(ModuleCatalog, on_delete=models.CASCADE)
    can_view = models.BooleanField(default=True)
    can_create = models.BooleanField(default=False)
    can_change = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)
    can_view_pii = models.BooleanField("Просмотр ПДн", default=False)
    can_export_pii = models.BooleanField("Экспорт ПДн", default=False)

    class Meta:
        verbose_name = "Право на модуль"
        verbose_name_plural = "Права на модули"
        unique_together = [("role", "module")]


class SubsystemMembership(models.Model):
    """Пользователь в подсистеме: организация + роль."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subsystem_memberships",
    )
    subsystem = models.ForeignKey(
        Subsystem, on_delete=models.CASCADE, related_name="memberships"
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_default = models.BooleanField("По умолчанию", default=False)

    class Meta:
        verbose_name = "Членство в подсистеме"
        verbose_name_plural = "Членства в подсистемах"
        unique_together = [("user", "subsystem", "organization", "role")]

    def __str__(self):
        return f"{self.user} @ {self.subsystem.code}"


from delayu.models_business import *  # noqa: E402, F403
from delayu.models_uzhv import *  # noqa: E402, F403
