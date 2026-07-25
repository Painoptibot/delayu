"""Odysseus workspace settings (platform module M87)."""

from django.db import models


class OdysseusSettings(models.Model):
    class EmbedMode(models.TextChoices):
        IFRAME = "iframe", "Iframe"
        NEW_TAB = "new_tab", "Новая вкладка"
        PROXY_SHELL = "proxy_shell", "Proxy shell"

    class AuthMode(models.TextChoices):
        NONE_DEV = "none_dev", "Dev (без auth bridge)"
        SHARED_SECRET = "shared_secret", "Shared secret"
        HEADER_BRIDGE = "header_bridge", "Header bridge"

    subsystem = models.OneToOneField(
        "Subsystem",
        on_delete=models.CASCADE,
        related_name="odysseus_settings",
    )
    enabled = models.BooleanField(default=False)
    base_url = models.URLField(default="http://127.0.0.1:7000")
    embed_mode = models.CharField(
        max_length=16, choices=EmbedMode.choices, default=EmbedMode.PROXY_SHELL
    )
    pinned_ref = models.CharField(max_length=128, blank=True)
    previous_pinned_ref = models.CharField(max_length=128, blank=True)
    upstream_url = models.URLField(
        default="https://github.com/odysseus-dev/odysseus.git", blank=True
    )
    vendor_path = models.CharField(max_length=255, default="vendor/odysseus")
    auth_mode = models.CharField(
        max_length=32, choices=AuthMode.choices, default=AuthMode.NONE_DEV
    )
    shared_secret = models.CharField(max_length=255, blank=True)
    allowed_path_prefixes = models.JSONField(default=list, blank=True)
    timeout_s = models.PositiveSmallIntegerField(default=30)
    role_allowlist = models.JSONField(default=list, blank=True)
    last_health_at = models.DateTimeField(null=True, blank=True)
    last_health_ok = models.BooleanField(default=False)
    options = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки Odysseus"
        verbose_name_plural = "Настройки Odysseus"

    def __str__(self):
        return f"OdysseusSettings({self.subsystem_id})"

    def get_allowed_path_prefixes(self) -> list[str]:
        raw = self.allowed_path_prefixes or []
        if raw:
            return list(raw)
        return ["/", "/api/", "/assets/", "/static/"]

    def get_role_allowlist(self) -> list[str]:
        raw = self.role_allowlist or []
        if raw:
            return list(raw)
        return ["invest_admin", "invest_dept"]
