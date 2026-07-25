from django.contrib import admin

from .models import (
    InvestAutomationConfig,
    InvestAutomationRun,
    InvestExternalTask,
    InvestHandoff,
    InvestImportBatch,
    InvestImportRow,
    InvestIntegrationEvent,
    InvestPackage,
    InvestPackageItem,
    InvestProject,
    InvestProjectSite,
    InvestRoadmapItem,
    InvestSite,
    InvestSmevRequest,
    ModuleCatalog,
    Organization,
    Role,
    RoleModulePermission,
    Subsystem,
    SubsystemMembership,
    SubsystemModule,
)


class SubsystemModuleInline(admin.TabularInline):
    model = SubsystemModule
    extra = 0
    autocomplete_fields = ["module"]


@admin.register(ModuleCatalog)
class ModuleCatalogAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "group", "is_core", "is_active", "sort_order")
    list_filter = ("group", "is_core", "is_active")
    search_fields = ("code", "name")


@admin.register(Subsystem)
class SubsystemAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("code", "name")
    inlines = [SubsystemModuleInline]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "subsystem", "is_active")
    list_filter = ("subsystem", "is_active")
    search_fields = ("name", "code")


class RoleModulePermissionInline(admin.TabularInline):
    model = RoleModulePermission
    extra = 0


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "subsystem", "is_system")
    list_filter = ("subsystem", "is_system")
    inlines = [RoleModulePermissionInline]


@admin.register(SubsystemMembership)
class SubsystemMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "subsystem", "organization", "role", "is_default")
    list_filter = ("subsystem", "role")


@admin.register(InvestProject)
class InvestProjectAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subsystem", "organization", "stage", "owner")
    list_filter = ("subsystem", "organization", "stage", "funnel")
    search_fields = ("code", "name", "investor_name")


@admin.register(InvestSite)
class InvestSiteAdmin(admin.ModelAdmin):
    list_display = ("cadastral_number", "name", "subsystem", "organization", "status")
    list_filter = ("subsystem", "organization", "status")
    search_fields = ("cadastral_number", "name")


@admin.register(InvestProjectSite)
class InvestProjectSiteAdmin(admin.ModelAdmin):
    list_display = ("project", "site", "role")
    list_filter = ("role",)


@admin.register(InvestHandoff)
class InvestHandoffAdmin(admin.ModelAdmin):
    list_display = ("project", "status", "requested_by", "decided_by", "created_at")
    list_filter = ("status",)


@admin.register(InvestPackage)
class InvestPackageAdmin(admin.ModelAdmin):
    list_display = ("project", "is_active", "created_at")
    list_filter = ("is_active",)


@admin.register(InvestPackageItem)
class InvestPackageItemAdmin(admin.ModelAdmin):
    list_display = ("package", "code", "title", "status", "required", "due_at")
    list_filter = ("status", "required")
    search_fields = ("code", "title")


@admin.register(InvestRoadmapItem)
class InvestRoadmapItemAdmin(admin.ModelAdmin):
    list_display = ("project", "code", "title", "status", "owner", "due_at")
    list_filter = ("status",)
    search_fields = ("code", "title")


@admin.register(InvestImportBatch)
class InvestImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "subsystem", "organization", "status", "created_at")
    list_filter = ("subsystem", "organization", "status")


@admin.register(InvestImportRow)
class InvestImportRowAdmin(admin.ModelAdmin):
    list_display = ("batch", "row_number", "action", "resolution", "target_project", "target_site")
    list_filter = ("action", "resolution")


@admin.register(InvestSmevRequest)
class InvestSmevRequestAdmin(admin.ModelAdmin):
    list_display = ("site", "service", "status", "is_mock", "created_at", "finished_at")
    list_filter = ("service", "status", "is_mock", "subsystem")
    search_fields = ("site__cadastral_number",)


@admin.register(InvestAutomationConfig)
class InvestAutomationConfigAdmin(admin.ModelAdmin):
    list_display = ("subsystem", "contract_version", "updated_at")
    search_fields = ("subsystem__code",)


@admin.register(InvestIntegrationEvent)
class InvestIntegrationEventAdmin(admin.ModelAdmin):
    list_display = (
        "correlation_id",
        "channel",
        "direction",
        "event_type",
        "status",
        "external_id",
        "retries",
        "created_at",
    )
    list_filter = ("channel", "direction", "status", "subsystem")
    search_fields = ("correlation_id", "external_id", "event_type")


@admin.register(InvestExternalTask)
class InvestExternalTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "project", "organization", "due_at", "escalated_level")
    list_filter = ("kind", "status", "subsystem")
    search_fields = ("title", "project__code")


@admin.register(InvestAutomationRun)
class InvestAutomationRunAdmin(admin.ModelAdmin):
    list_display = ("id", "subsystem", "started_at", "finished_at")
    list_filter = ("subsystem",)


from delayu import admin_business  # noqa: F401, E402
