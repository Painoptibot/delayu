from django.contrib import admin

from .models import (
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


from delayu import admin_business  # noqa: F401, E402
