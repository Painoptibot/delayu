"""Инвестконтур Кубани — доменные модели (тенант = Subsystem)."""
from django.conf import settings
from django.db import models


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
    industry = models.CharField("Отрасль", max_length=128, blank=True)
    funnel = models.CharField(max_length=16, choices=Funnel.choices, default=Funnel.ATTRACTION)
    stage = models.CharField("Стадия", max_length=32, default="lead")
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="invest_projects_owned",
    )
    investment_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    jobs_count = models.PositiveIntegerField(null=True, blank=True)
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
    area_ha = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    land_category = models.CharField(max_length=128, blank=True)
    vri = models.CharField("ВРИ", max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    completeness_pct = models.PositiveSmallIntegerField(default=0)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
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
