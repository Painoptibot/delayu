from django.contrib import admin

from delayu.models import (
    ActivityEvent,
    AiRequestLog,
    AuditLog,
    BPMInstance,
    BPMTask,
    BPMTemplate,
    CaseFile,
    ChatMessage,
    ChatRoom,
    Correspondence,
    Department,
    DocumentFile,
    IntegrationEndpoint,
    IntegrationMessage,
    KnowledgeArticle,
    Notification,
    NSIClassifier,
    NSIValue,
    RegistryRecord,
    RegistryType,
    ReportRun,
    ReportTemplate,
    TaskItem,
)


@admin.register(CaseFile)
class CaseFileAdmin(admin.ModelAdmin):
    list_display = ("number", "title", "status", "subsystem", "assignee", "due_date")
    list_filter = ("subsystem", "status", "is_archived")
    search_fields = ("number", "title")


@admin.register(TaskItem)
class TaskItemAdmin(admin.ModelAdmin):
    list_display = ("title", "kanban_column", "assignee", "due_date", "subsystem")
    list_filter = ("kanban_column", "subsystem")


@admin.register(Correspondence)
class CorrespondenceAdmin(admin.ModelAdmin):
    list_display = ("reg_number", "direction", "subject", "status", "subsystem")
    list_filter = ("direction", "status")


@admin.register(DocumentFile)
class DocumentFileAdmin(admin.ModelAdmin):
    list_display = ("title", "version", "is_signed", "subsystem")


@admin.register(RegistryType)
class RegistryTypeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subsystem")


@admin.register(RegistryRecord)
class RegistryRecordAdmin(admin.ModelAdmin):
    list_display = ("registry_type", "external_id", "created_at")


@admin.register(BPMTemplate)
class BPMTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "subsystem")


@admin.register(BPMInstance)
class BPMInstanceAdmin(admin.ModelAdmin):
    list_display = ("case", "template", "status", "current_step_id")


@admin.register(BPMTask)
class BPMTaskAdmin(admin.ModelAdmin):
    list_display = ("step_name", "assignee", "status", "instance")


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("name", "subsystem")
    filter_horizontal = ("members",)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "author", "created_at")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "created_at")
    list_filter = ("is_read",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "user", "action", "model_name")
    readonly_fields = (
        "user",
        "subsystem",
        "action",
        "model_name",
        "object_id",
        "payload",
        "ip_address",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(KnowledgeArticle)
class KnowledgeArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "subsystem")


@admin.register(AiRequestLog)
class AiRequestLogAdmin(admin.ModelAdmin):
    list_display = ("module_code", "user", "created_at")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization")


@admin.register(IntegrationEndpoint)
class IntegrationEndpointAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "endpoint_type", "is_active")


@admin.register(ReportTemplate)
class ReportTemplateAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "query_key", "subsystem")
