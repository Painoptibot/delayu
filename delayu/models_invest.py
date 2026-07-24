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
