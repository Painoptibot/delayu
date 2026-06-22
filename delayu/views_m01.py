"""M01 — подсистемы, каталог модулей, журнал аудита."""
from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from delayu.forms_m01 import SubsystemCloneForm, SubsystemEditForm, SubsystemWizardForm
from delayu.mixins import CriticalReauthMixin, ModulePermissionMixin
from delayu.models import ModuleCatalog, Subsystem, SubsystemModule
from delayu.models_business import AuditLog
from delayu.services import audit
from delayu.services.access import user_can
from delayu.services.subsystems import (
    clone_subsystem,
    grouped_modules,
    publish_subsystem,
    subsystem_card_context,
)
from delayu.views_platform import _ctx_membership


class SubsystemsListView(ModulePermissionMixin, ListView):
    module_code = "M01"
    model = Subsystem
    template_name = "platform/admin/subsystems/list.html"
    context_object_name = "subsystems"

    def get_queryset(self):
        return Subsystem.objects.annotate(
            enabled_module_count=Count(
                "module_links", filter=Q(module_links__enabled=True)
            ),
            users_count=Count("memberships"),
        ).order_by("-updated_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Подсистемы"
        ctx["can_create"] = user_can(self.request.user, "M01", "create")
        ctx["can_change"] = user_can(self.request.user, "M01", "change")
        ctx["can_delete"] = user_can(self.request.user, "M01", "delete")
        return ctx


class SubsystemWizardCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M01"
    required_action = "create"
    template_name = "platform/admin/subsystems/wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        form = kwargs.get("form") or SubsystemWizardForm()
        ctx["page_title"] = "Новая подсистема"
        ctx["form"] = form
        ctx["module_groups"] = grouped_modules()
        ctx["selected_codes"] = list(form.fields["module_codes"].initial or [])
        return ctx

    def post(self, request, *args, **kwargs):
        form = SubsystemWizardForm(request.POST)
        if form.is_valid():
            subsystem = form.save(creator_user=request.user)
            audit.log_action(
                request.user,
                subsystem,
                "subsystem.create",
                "Subsystem",
                subsystem.pk,
                {"code": subsystem.code},
                request,
            )
            messages.success(request, f"Подсистема «{subsystem.name}» создана.")
            return redirect(f"/administration/subsystems/?open={subsystem.pk}")
        ctx = self.get_context_data(form=form)
        ctx["selected_codes"] = request.POST.getlist("module_codes")
        return self.render_to_response(ctx)


class SubsystemModalView(ModulePermissionMixin, View):
    module_code = "M01"

    def get(self, request, pk):
        subsystem = get_object_or_404(Subsystem, pk=pk)
        ctx = subsystem_card_context(subsystem)
        ctx["module_links"] = SubsystemModule.objects.filter(
            subsystem=subsystem
        ).select_related("module")
        ctx["can_change"] = user_can(request.user, "M01", "change")
        ctx["can_create"] = user_can(request.user, "M01", "create")
        ctx["edit_mode"] = request.GET.get("mode") == "edit"
        if ctx["edit_mode"]:
            ctx["edit_form"] = SubsystemEditForm(instance=subsystem)
            ctx["module_groups"] = grouped_modules()
        return render(request, "platform/admin/subsystems/_modal_body.html", ctx)


class SubsystemUpdateView(ModulePermissionMixin, View):
    module_code = "M01"
    required_action = "change"

    def post(self, request, pk):
        subsystem = get_object_or_404(Subsystem, pk=pk)
        form = SubsystemEditForm(request.POST, instance=subsystem)
        if form.is_valid():
            form.save()
            audit.log_action(
                request.user,
                subsystem,
                "subsystem.update",
                "Subsystem",
                subsystem.pk,
                request=request,
            )
            messages.success(request, "Подсистема сохранена.")
            return redirect(f"/administration/subsystems/?open={pk}")
        ctx = subsystem_card_context(subsystem)
        ctx["edit_form"] = form
        ctx["edit_mode"] = True
        ctx["can_change"] = True
        ctx["module_groups"] = grouped_modules()
        ctx["module_links"] = SubsystemModule.objects.filter(
            subsystem=subsystem
        ).select_related("module")
        return render(request, "platform/admin/subsystems/_modal_body.html", ctx)


class SubsystemPublishView(ModulePermissionMixin, View):
    module_code = "M01"
    required_action = "change"

    def post(self, request, pk):
        subsystem = get_object_or_404(Subsystem, pk=pk)
        version = request.POST.get("config_version", "").strip()
        publish_subsystem(subsystem, version)
        audit.log_action(
            request.user,
            subsystem,
            "subsystem.publish",
            "Subsystem",
            subsystem.pk,
            {"version": version or subsystem.config_version},
            request,
        )
        messages.success(request, f"Подсистема «{subsystem.name}» опубликована.")
        return redirect(f"/administration/subsystems/?open={pk}")


class SubsystemArchiveView(ModulePermissionMixin, View):
    module_code = "M01"
    required_action = "delete"

    def post(self, request, pk):
        subsystem = get_object_or_404(Subsystem, pk=pk)
        subsystem.status = Subsystem.Status.ARCHIVED
        subsystem.save(update_fields=["status", "updated_at"])
        audit.log_action(
            request.user,
            subsystem,
            "subsystem.archive",
            "Subsystem",
            subsystem.pk,
            request=request,
        )
        messages.success(request, f"Подсистема «{subsystem.name}» в архиве.")
        return redirect("platform-subsystems")


class SubsystemCloneView(ModulePermissionMixin, View):
    module_code = "M01"
    required_action = "create"

    def post(self, request, pk):
        source = get_object_or_404(Subsystem, pk=pk)
        form = SubsystemCloneForm(request.POST)
        if form.is_valid():
            try:
                new_sub = clone_subsystem(
                    source,
                    form.cleaned_data["code"].strip().lower(),
                    form.cleaned_data["name"],
                )
                audit.log_action(
                    request.user,
                    new_sub,
                    "subsystem.clone",
                    "Subsystem",
                    new_sub.pk,
                    {"from": source.code},
                    request,
                )
                messages.success(request, f"Создан клон: {new_sub.name}")
                return redirect(f"/administration/subsystems/?open={new_sub.pk}")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Укажите код и название клона.")
        return redirect("platform-subsystems")


class SubsystemModuleToggleView(ModulePermissionMixin, View):
    module_code = "M01"
    required_action = "change"

    def post(self, request, pk):
        link = get_object_or_404(SubsystemModule, pk=pk)
        link.enabled = not link.enabled
        link.save(update_fields=["enabled"])
        audit.log_action(
            request.user,
            link.subsystem,
            "subsystem.module_toggle",
            "SubsystemModule",
            link.pk,
            {"module": link.module.code, "enabled": link.enabled},
            request,
        )
        return redirect(f"/administration/subsystems/?open={link.subsystem_id}")


class ModuleCatalogAdminView(ModulePermissionMixin, ListView):
    module_code = "M01"
    model = ModuleCatalog
    template_name = "platform/admin/modules/list.html"
    context_object_name = "modules"
    paginate_by = 50

    def get_queryset(self):
        qs = ModuleCatalog.objects.filter(is_active=True).order_by("sort_order", "code")
        group = self.request.GET.get("group")
        if group:
            qs = qs.filter(group=group)
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Каталог модулей"
        ctx["groups"] = ModuleCatalog.Group.choices
        ctx["active_group"] = self.request.GET.get("group", "")
        ctx["search_q"] = self.request.GET.get("q", "")
        return ctx


class ModuleCatalogModalView(ModulePermissionMixin, View):
    module_code = "M01"

    def get(self, request, pk):
        mod = get_object_or_404(ModuleCatalog, pk=pk)
        subsystems = Subsystem.objects.filter(
            module_links__module=mod, module_links__enabled=True
        ).distinct()[:15]
        return render(
            request,
            "platform/admin/modules/_modal_body.html",
            {"module": mod, "subsystems": subsystems},
        )


class AuditLogAdminView(ModulePermissionMixin, ListView):
    module_code = "M01"
    model = AuditLog
    template_name = "platform/admin/audit/list.html"
    context_object_name = "logs"
    paginate_by = 40

    def get_queryset(self):
        m = _ctx_membership(self)
        qs = AuditLog.objects.filter(subsystem=m.subsystem).select_related("user")
        action = self.request.GET.get("action", "").strip()
        if action:
            qs = qs.filter(action__icontains=action)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Журнал аудита"
        ctx["filter_action"] = self.request.GET.get("action", "")
        m = _ctx_membership(self)
        from delayu.services.audit import list_audit_snapshots

        ctx["audit_snapshots"] = list_audit_snapshots(subsystem_code=m.subsystem.code, limit=8)
        from delayu.forms_exploitation import SiemExportConfigForm
        from delayu.services.siem_export import get_or_create_siem_config

        siem = get_or_create_siem_config(m.subsystem)
        ctx["siem_config"] = siem
        ctx["siem_form"] = SiemExportConfigForm(instance=siem)
        return ctx


class AuditSnapshotCreateView(CriticalReauthMixin, ModulePermissionMixin, View):
    module_code = "M01"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import save_audit_snapshot

        mask = request.POST.get("mask_pii") == "1"
        action = request.POST.get("action", "").strip()
        result = save_audit_snapshot(m.subsystem, action=action, mask_pii=mask)
        messages.success(request, f"Снимок сохранён: {result['filename']} ({result['rows']} строк)")
        qs = f"?action={action}" if action else ""
        return redirect(f"{reverse('platform-audit')}{qs}")


class AuditLogExportView(CriticalReauthMixin, ModulePermissionMixin, View):
    module_code = "M01"
    reauth_on_get = True

    def get(self, request):
        m = _ctx_membership(self)
        from delayu.services.audit import export_audit_csv

        mask = request.GET.get("mask_pii") == "1"
        action = request.GET.get("action", "").strip()
        return export_audit_csv(m.subsystem, action=action, mask_pii=mask)


class SiemExportConfigView(CriticalReauthMixin, ModulePermissionMixin, View):
    module_code = "M01"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.forms_exploitation import SiemExportConfigForm
        from delayu.services.siem_export import get_or_create_siem_config

        cfg = get_or_create_siem_config(m.subsystem)
        form = SiemExportConfigForm(request.POST, instance=cfg)
        if form.is_valid():
            form.save()
            audit.log_action(
                request.user,
                m.subsystem,
                "siem.config.update",
                "SiemExportConfig",
                cfg.pk,
                request=request,
            )
            messages.success(request, "Настройки экспорта в SIEM сохранены.")
        else:
            messages.error(request, "Проверьте URL webhook SIEM.")
        return redirect("platform-audit")


class SiemExportPushView(CriticalReauthMixin, ModulePermissionMixin, View):
    module_code = "M01"

    def post(self, request):
        m = _ctx_membership(self)
        from delayu.services.siem_export import push_siem_events

        result = push_siem_events(m.subsystem)
        if result.get("skipped"):
            messages.warning(request, "Экспорт в SIEM отключён или не настроен webhook.")
        elif result.get("ok"):
            messages.success(request, f"Отправлено событий: {result.get('pushed', 0)}.")
        else:
            messages.error(request, f"Ошибка SIEM: {result.get('error', 'неизвестно')}")
        return redirect("platform-audit")


class AuditLogModalView(ModulePermissionMixin, View):
    module_code = "M01"

    def get(self, request, pk):
        m = _ctx_membership(self)
        entry = get_object_or_404(AuditLog, pk=pk, subsystem=m.subsystem)
        return render(
            request,
            "platform/admin/audit/_modal_body.html",
            {"entry": entry},
        )
