"""Лицевые счета УЖВ — открытие, состав семьи, выписки."""
from __future__ import annotations

from delayu.models_uzhv import (
    HousingContract,
    HousingPersonalAccount,
    HousingPersonalAccountHistory,
    HousingPersonalAccountMember,
    MunicipalPremise,
)


def suggest_account_number(premise: MunicipalPremise) -> str:
    b_id = premise.building_id
    return f"ЛС-{b_id}-{premise.number}"


def sync_tenant_from_contract(account: HousingPersonalAccount) -> None:
    contract = (
        HousingContract.objects.filter(
            premise=account.premise,
            is_active=True,
            subsystem=account.subsystem,
        )
        .select_related("citizen")
        .order_by("-signed_at")
        .first()
    )
    if contract and not account.tenant_citizen_id:
        account.tenant_citizen = contract.citizen
        account.save(update_fields=["tenant_citizen", "updated_at"])


def ensure_personal_account(
    premise: MunicipalPremise, *, user=None, create: bool = True
) -> HousingPersonalAccount | None:
    try:
        account = premise.personal_account
        sync_tenant_from_contract(account)
        return account
    except HousingPersonalAccount.DoesNotExist:
        if not create:
            return None
    subsystem = premise.building.subsystem
    account = HousingPersonalAccount.objects.create(
        subsystem=subsystem,
        premise=premise,
        account_number=suggest_account_number(premise),
        total_area_sqm=premise.area_sqm,
        living_area_sqm=premise.area_sqm,
    )
    sync_tenant_from_contract(account)
    if user:
        record_account_history(account, "Открыт лицевой счёт", user)
    return account


def record_account_history(
    account: HousingPersonalAccount, description: str, user=None
) -> HousingPersonalAccountHistory:
    return HousingPersonalAccountHistory.objects.create(
        account=account,
        description=description.strip(),
        changed_by=user,
    )


def build_account_members_lines(account: HousingPersonalAccount) -> str:
    members = account.members.filter(registered_to__isnull=True).order_by("sort_order", "full_name")
    if not members.exists() and account.tenant_citizen_id:
        return account.tenant_citizen.full_name
    lines = []
    for m in members:
        line = f"- {m.full_name} ({m.get_relation_display()})"
        if m.birth_date:
            line += f", {m.birth_date:%d.%m.%Y}"
        lines.append(line)
    return "\n".join(lines) or "—"


def build_account_extract_context(account: HousingPersonalAccount) -> dict[str, str]:
    from delayu.services.uzhv_documents import timezone_now_str

    premise = account.premise
    building = premise.building
    tenant = account.tenant_citizen
    tenant_name = tenant.full_name if tenant else "—"
    tenant_snils = tenant.snils if tenant else ""
    return {
        "account_number": account.account_number,
        "premise_address": str(premise),
        "building_address": building.address,
        "premise_number": premise.number,
        "living_area": str(account.living_area_sqm or premise.area_sqm or "—"),
        "total_area": str(account.total_area_sqm or premise.area_sqm or "—"),
        "rooms": str(premise.rooms or "—"),
        "tenant_name": tenant_name,
        "tenant_snils": tenant_snils,
        "tenant_address": tenant.reg_address if tenant else "",
        "utility_services": account.utility_services or "—",
        "members_list": build_account_members_lines(account),
        "opened_at": account.opened_at.strftime("%d.%m.%Y"),
        "account_status": "Открыт" if account.is_active else "Закрыт",
        "today": timezone_now_str(),
    }
