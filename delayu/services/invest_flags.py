"""Feature-flags и конфиг автоматизации инвестконтура (п.27–29)."""
from __future__ import annotations

from delayu.models_invest import InvestAutomationConfig

DEFAULT_FIELD_MAPPING_V1 = {
    "TITLE": "name",
    "UF_INVESTOR": "investor_name",
    "UF_INDUSTRY": "industry",
    "UF_INVESTMENT": "investment_amount",
    "UF_JOBS": "jobs_count",
    "UF_CONTACT": "contact_person",
    "UF_PHONE": "contact_phone",
    "UF_EMAIL": "contact_email",
    "UF_CADASTRE": "cadastral_number",
    "UF_MO_CODE": "organization_code",
    "STAGE_ID": "bitrix_stage",
}

DEFAULT_STAGE_MAPPING_V1 = {
    "NEW": ("attraction", "lead"),
    "PREPARATION": ("attraction", "qualify"),
    "SITE": ("attraction", "site_pick"),
    "PACKAGE": ("attraction", "package_ready"),
    "HANDOFF": ("attraction", "handoff"),
    "SUPPORT": ("support", "accepted"),
}


def ensure_automation_config(subsystem) -> InvestAutomationConfig:
    cfg, created = InvestAutomationConfig.objects.get_or_create(
        subsystem=subsystem,
        defaults={
            "flags": dict(InvestAutomationConfig.DEFAULT_FLAGS),
            "contract_version": "v1",
            "field_mapping": dict(DEFAULT_FIELD_MAPPING_V1),
            "stage_mapping": dict(DEFAULT_STAGE_MAPPING_V1),
            "bitrix_webhook_token": f"invest-{subsystem.code}-sandbox",
        },
    )
    if not created and not cfg.field_mapping:
        cfg.field_mapping = dict(DEFAULT_FIELD_MAPPING_V1)
        cfg.stage_mapping = dict(DEFAULT_STAGE_MAPPING_V1)
        cfg.save(update_fields=["field_mapping", "stage_mapping", "updated_at"])
    return cfg


def flag_enabled(subsystem, name: str, default: bool = False) -> bool:
    return ensure_automation_config(subsystem).flag(name, default)
