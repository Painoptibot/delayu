"""M01 — подсистемы, матрица модулей, клонирование."""
from collections import defaultdict
from datetime import datetime

from django.db import transaction
from django.utils import timezone

from delayu.models import (
    LicenseEntitlement,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)


def grouped_modules():
    """Модули каталога, сгруппированные по group: [(label, [modules]), ...]."""
    groups = defaultdict(list)
    for mod in ModuleCatalog.objects.filter(is_active=True).order_by("sort_order", "code"):
        groups[mod.group].append(mod)
    labels = dict(ModuleCatalog.Group.choices)
    return [(labels.get(key, key), mods) for key, mods in sorted(groups.items())]


def save_module_matrix(subsystem, selected_codes):
    selected = set(selected_codes or [])
    for mod in ModuleCatalog.objects.filter(is_active=True):
        SubsystemModule.objects.update_or_create(
            subsystem=subsystem,
            module=mod,
            defaults={"enabled": mod.code in selected},
        )
        LicenseEntitlement.objects.update_or_create(
            subsystem=subsystem,
            module=mod,
            defaults={"valid_until": None},
        )


@transaction.atomic
def provision_subsystem(subsystem, module_codes, creator_user=None):
    """Организация, роли, права администратора, членство создателя."""
    save_module_matrix(subsystem, module_codes)
    org, _ = Organization.objects.update_or_create(
        subsystem=subsystem,
        code="main",
        defaults={"name": "Головная организация"},
    )
    admin_role, _ = Role.objects.update_or_create(
        subsystem=subsystem,
        code="admin",
        defaults={"name": "Администратор подсистемы", "is_system": True},
    )
    Role.objects.update_or_create(
        subsystem=subsystem,
        code="specialist",
        defaults={"name": "Специалист", "is_system": True},
    )
    Role.objects.update_or_create(
        subsystem=subsystem,
        code="manager",
        defaults={"name": "Руководитель", "is_system": True},
    )
    for role in Role.objects.filter(subsystem=subsystem):
        for mod in ModuleCatalog.objects.filter(is_active=True):
            is_admin = role.code == "admin"
            RoleModulePermission.objects.update_or_create(
                role=role,
                module=mod,
                defaults={
                    "can_view": True,
                    "can_create": is_admin or role.code == "specialist",
                    "can_change": is_admin or role.code in ("specialist", "manager"),
                    "can_delete": is_admin,
                },
            )
    if creator_user and creator_user.is_authenticated:
        SubsystemMembership.objects.update_or_create(
            user=creator_user,
            subsystem=subsystem,
            organization=org,
            role=admin_role,
            defaults={"is_default": False},
        )
    return subsystem


def subsystem_card_context(subsystem):
    links = SubsystemModule.objects.filter(subsystem=subsystem).select_related("module")
    enabled = [lk for lk in links if lk.enabled]
    return {
        "subsystem": subsystem,
        "enabled_count": len(enabled),
        "total_links": links.count(),
        "orgs_count": subsystem.organizations.count(),
        "users_count": SubsystemMembership.objects.filter(subsystem=subsystem).count(),
        "roles_count": subsystem.roles.count(),
        "enabled_modules": [lk.module for lk in enabled[:20]],
        "has_more_modules": len(enabled) > 20,
    }


@transaction.atomic
def publish_subsystem(subsystem, version_label=""):
    subsystem.status = Subsystem.Status.ACTIVE
    subsystem.published_at = timezone.now()
    if version_label:
        subsystem.config_version = version_label
    subsystem.save(update_fields=["status", "published_at", "config_version", "updated_at"])
    return subsystem


@transaction.atomic
def clone_subsystem(source, new_code, new_name):
    if Subsystem.objects.filter(code=new_code).exists():
        raise ValueError("Подсистема с таким кодом уже существует")
    new_sub = Subsystem.objects.create(
        code=new_code,
        name=new_name,
        description=f"Клон: {source.description}",
        status=Subsystem.Status.DRAFT,
        primary_color=source.primary_color,
        industry_template=source.industry_template,
    )
    codes = list(
        source.module_links.filter(enabled=True).values_list("module__code", flat=True)
    )
    provision_subsystem(new_sub, codes, creator_user=None)
    for org in source.organizations.all():
        Organization.objects.update_or_create(
            subsystem=new_sub,
            code=org.code,
            defaults={"name": org.name, "is_active": org.is_active},
        )
    return new_sub
