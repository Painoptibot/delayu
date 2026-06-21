"""M02 — Роли: список, мастер, модальная карточка, копирование."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_roles import RoleCopyForm, RoleEditForm, RoleWizardForm
from delayu.mixins import ModulePermissionMixin
from django.contrib.auth import get_user_model

from delayu.models import Role, SubsystemMembership

User = get_user_model()
from delayu.services.access import user_can
from delayu.services.roles import (
    PERM_ACTIONS,
    build_matrix_rows,
    copy_role,
    enabled_modules_for_subsystem,
    role_card_context,
)
from delayu.views_platform import _ctx_membership


class RolesListView(ModulePermissionMixin, TemplateView):
    module_code = "M02"
    template_name = "platform/admin/roles/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Роли и права"
        roles = Role.objects.filter(subsystem=m.subsystem).order_by("name")
        role_list = []
        for r in roles:
            mems = SubsystemMembership.objects.filter(role=r).select_related("user")[:5]
            role_list.append(
                {
                    "role": r,
                    "users_count": SubsystemMembership.objects.filter(role=r).count(),
                    "sample_users": [m.user for m in mems[:4]],
                }
            )
        ctx["role_list"] = role_list
        ctx["members_with_roles"] = (
            SubsystemMembership.objects.filter(subsystem=m.subsystem)
            .select_related("user", "role", "organization")
            .order_by("role__name", "user__username")[:100]
        )
        ctx["can_create"] = user_can(self.request.user, "M02", "create")
        ctx["can_change"] = user_can(self.request.user, "M02", "change")
        ctx["can_delete"] = user_can(self.request.user, "M02", "delete")
        return ctx


class RoleWizardCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M02"
    required_action = "create"
    template_name = "platform/admin/roles/wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        form = kwargs.get("form") or RoleWizardForm(subsystem=m.subsystem)
        ctx["page_title"] = "Новая роль"
        ctx["form"] = form
        ctx["matrix_rows"] = build_matrix_rows(form, m.subsystem)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = RoleWizardForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            role = form.save()
            messages.success(request, f"Роль «{role.name}» создана.")
            return redirect("platform-roles")
        return self.render_to_response(self.get_context_data(form=form))


class RoleModalView(ModulePermissionMixin, View):
    module_code = "M02"

    def get(self, request, pk):
        m = _ctx_membership(self)
        role = get_object_or_404(Role, pk=pk, subsystem=m.subsystem)
        ctx = role_card_context(role)
        ctx["can_change"] = user_can(request.user, "M02", "change")
        ctx["can_delete"] = user_can(request.user, "M02", "delete")
        ctx["edit_mode"] = request.GET.get("mode") == "edit"
        if ctx["edit_mode"]:
            edit_form = RoleEditForm(instance=role, subsystem=m.subsystem)
            ctx["edit_form"] = edit_form
            ctx["matrix_rows"] = build_matrix_rows(edit_form, m.subsystem)
        return render(request, "platform/admin/roles/_modal_body.html", ctx)


class RoleUpdateView(ModulePermissionMixin, View):
    module_code = "M02"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        role = get_object_or_404(Role, pk=pk, subsystem=m.subsystem)
        form = RoleEditForm(request.POST, instance=role, subsystem=m.subsystem)
        if form.is_valid():
            form.save()
            messages.success(request, "Роль сохранена.")
            from django.urls import reverse

            return redirect(reverse("platform-roles") + f"?open={pk}")
        ctx = role_card_context(role)
        ctx["edit_form"] = form
        ctx["edit_mode"] = True
        ctx["can_change"] = True
        ctx["matrix_rows"] = build_matrix_rows(form, m.subsystem)
        return render(request, "platform/admin/roles/_modal_body.html", ctx)


class RoleDeleteView(ModulePermissionMixin, View):
    module_code = "M02"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        role = get_object_or_404(Role, pk=pk, subsystem=m.subsystem)
        if role.is_system:
            messages.error(request, "Системную роль нельзя удалить.")
            return redirect("platform-roles")
        if SubsystemMembership.objects.filter(role=role).exists():
            messages.error(request, "Роль назначена пользователям — удаление невозможно.")
            return redirect("platform-roles")
        name = role.name
        role.delete()
        messages.success(request, f"Роль «{name}» удалена.")
        return redirect("platform-roles")


class RoleCopyView(ModulePermissionMixin, View):
    module_code = "M02"
    required_action = "create"

    def post(self, request, pk):
        m = _ctx_membership(self)
        source = get_object_or_404(Role, pk=pk, subsystem=m.subsystem)
        form = RoleCopyForm(request.POST)
        if form.is_valid():
            try:
                new_role = copy_role(
                    source,
                    form.cleaned_data["code"].strip().lower(),
                    form.cleaned_data["name"],
                )
                messages.success(request, f"Создана копия роли: {new_role.name}")
                return redirect(f"/administration/roles/?open={new_role.pk}")
            except ValueError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, "Проверьте код и наименование новой роли.")
        return redirect("platform-roles")
