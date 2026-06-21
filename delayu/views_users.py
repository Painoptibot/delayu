"""M03 — Пользователи: список, мастер, модальная карточка."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_users import UserEditForm, UserWizardForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import SubsystemMembership
from delayu.services.access import user_can
from delayu.services.users import deactivate_user, user_card_context
from delayu.views_platform import _ctx_membership

User = get_user_model()


class UsersAdminView(ModulePermissionMixin, TemplateView):
    module_code = "M03"
    template_name = "platform/admin/users/list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Пользователи"
        ctx["memberships"] = (
            SubsystemMembership.objects.filter(subsystem=m.subsystem)
            .select_related("user", "role", "organization", "user__delayu_profile")
            .order_by("user__last_name", "user__username")
        )
        ctx["can_create"] = user_can(self.request.user, "M03", "create")
        ctx["can_change"] = user_can(self.request.user, "M03", "change")
        ctx["can_delete"] = user_can(self.request.user, "M03", "delete")
        return ctx


class UserWizardCreateView(ModulePermissionMixin, TemplateView):
    module_code = "M03"
    required_action = "create"
    template_name = "platform/admin/users/wizard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Новый пользователь"
        ctx["form"] = UserWizardForm(subsystem=m.subsystem)
        return ctx

    def post(self, request, *args, **kwargs):
        m = _ctx_membership(self)
        form = UserWizardForm(request.POST, subsystem=m.subsystem)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Пользователь {user.username} создан.")
            return redirect("platform-users")
        return self.render_to_response(
            self.get_context_data(form=form, page_title="Новый пользователь")
        )


class UserModalView(ModulePermissionMixin, View):
    module_code = "M03"

    def get(self, request, pk):
        m = _ctx_membership(self)
        membership = get_object_or_404(
            SubsystemMembership,
            pk=pk,
            subsystem=m.subsystem,
        )
        ctx = user_card_context(membership.user, membership)
        ctx["can_change"] = user_can(request.user, "M03", "change")
        ctx["edit_form"] = UserEditForm(
            user=membership.user,
            membership=membership,
            subsystem=m.subsystem,
        )
        ctx["edit_mode"] = request.GET.get("mode") == "edit"
        return render(request, "platform/admin/users/_modal_body.html", ctx)


class UserUpdateView(ModulePermissionMixin, View):
    module_code = "M03"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        membership = get_object_or_404(
            SubsystemMembership,
            pk=pk,
            subsystem=m.subsystem,
        )
        form = UserEditForm(
            request.POST,
            user=membership.user,
            membership=membership,
            subsystem=m.subsystem,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Данные пользователя сохранены.")
            return redirect(f"{reverse('platform-users')}?open={pk}")
        ctx = user_card_context(membership.user, membership)
        ctx["edit_form"] = form
        ctx["edit_mode"] = True
        ctx["can_change"] = True
        return render(request, "platform/admin/users/_modal_body.html", ctx)


class UserDeleteView(ModulePermissionMixin, View):
    module_code = "M03"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        membership = get_object_or_404(
            SubsystemMembership,
            pk=pk,
            subsystem=m.subsystem,
        )
        if membership.user_id == request.user.id:
            messages.error(request, "Нельзя заблокировать собственную учётную запись.")
            return redirect("platform-users")
        deactivate_user(membership.user)
        messages.success(request, f"Пользователь {membership.user.username} заблокирован.")
        return redirect("platform-users")
