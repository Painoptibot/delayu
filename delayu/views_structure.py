"""M04 — Структура: дерево подразделений, должности, назначения."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import TemplateView

from delayu.forms_structure import DepartmentForm, PositionForm, UserAssignmentForm
from delayu.mixins import ModulePermissionMixin
from delayu.models import Organization
from delayu.models_business import Department, Position, UserAssignment
from delayu.services.access import user_can
from delayu.services.structure import (
    department_card_context,
    department_tree,
    flatten_tree,
    position_card_context,
)
from delayu.views_platform import _ctx_membership


class StructureAdminView(ModulePermissionMixin, TemplateView):
    module_code = "M04"
    template_name = "platform/admin/structure/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        m = _ctx_membership(self)
        ctx["page_title"] = "Организационная структура"
        orgs = Organization.objects.filter(subsystem=m.subsystem, is_active=True)
        org_id = self.request.GET.get("org")
        if org_id:
            org = orgs.filter(pk=org_id).first()
        else:
            org = m.organization
        if not org:
            org = orgs.first()
        ctx["organizations"] = orgs
        ctx["active_org"] = org
        if org:
            tree = department_tree(org)
            ctx["tree_rows"] = flatten_tree(tree)
        else:
            ctx["tree_rows"] = []
        ctx["can_create"] = user_can(self.request.user, "M04", "create")
        ctx["can_change"] = user_can(self.request.user, "M04", "change")
        ctx["can_delete"] = user_can(self.request.user, "M04", "delete")
        return ctx


class DepartmentWizardView(ModulePermissionMixin, TemplateView):
    module_code = "M04"
    required_action = "create"
    template_name = "platform/admin/structure/department_wizard.html"

    def _org(self, request):
        m = _ctx_membership(self)
        org_id = request.GET.get("org") or request.POST.get("organization")
        if org_id:
            return get_object_or_404(Organization, pk=org_id, subsystem=m.subsystem)
        return m.organization

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self._org(self.request)
        ctx["page_title"] = "Новое подразделение"
        ctx["organization"] = org
        ctx["form"] = kwargs.get("form") or DepartmentForm(organization=org)
        return ctx

    def post(self, request, *args, **kwargs):
        org = self._org(request)
        form = DepartmentForm(request.POST, organization=org)
        if form.is_valid():
            dept = form.save()
            messages.success(request, f"Подразделение «{dept.name}» создано.")
            return redirect(f"/administration/structure/?org={org.pk}&open_dept={dept.pk}")
        return self.render_to_response(self.get_context_data(form=form))


class DepartmentModalView(ModulePermissionMixin, View):
    module_code = "M04"

    def get(self, request, pk):
        m = _ctx_membership(self)
        dept = get_object_or_404(
            Department, pk=pk, organization__subsystem=m.subsystem
        )
        ctx = department_card_context(dept)
        ctx["can_change"] = user_can(request.user, "M04", "change")
        ctx["can_delete"] = user_can(request.user, "M04", "delete")
        ctx["edit_mode"] = request.GET.get("mode") == "edit"
        if ctx["edit_mode"]:
            ctx["edit_form"] = DepartmentForm(
                instance=dept, organization=dept.organization, department_pk=dept.pk
            )
            ctx["assignment_form"] = UserAssignmentForm(department=dept)
        return render(request, "platform/admin/structure/_department_modal.html", ctx)


class DepartmentUpdateView(ModulePermissionMixin, View):
    module_code = "M04"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        dept = get_object_or_404(
            Department, pk=pk, organization__subsystem=m.subsystem
        )
        if "assign_user" in request.POST:
            aform = UserAssignmentForm(request.POST, department=dept)
            if aform.is_valid():
                obj = aform.save(commit=False)
                obj.department = dept
                obj.save()
                messages.success(request, "Сотрудник назначен на должность.")
            else:
                messages.error(request, "Не удалось назначить сотрудника.")
            return redirect(
                f"/administration/structure/?org={dept.organization_id}&open_dept={dept.pk}"
            )
        form = DepartmentForm(
            request.POST,
            instance=dept,
            organization=dept.organization,
            department_pk=dept.pk,
        )
        if form.is_valid():
            form.save()
            messages.success(request, "Подразделение сохранено.")
            return redirect(
                f"/administration/structure/?org={dept.organization_id}&open_dept={dept.pk}"
            )
        ctx = department_card_context(dept)
        ctx["edit_form"] = form
        ctx["edit_mode"] = True
        ctx["can_change"] = True
        ctx["assignment_form"] = UserAssignmentForm(department=dept)
        return render(request, "platform/admin/structure/_department_modal.html", ctx)


class DepartmentDeleteView(ModulePermissionMixin, View):
    module_code = "M04"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        dept = get_object_or_404(
            Department, pk=pk, organization__subsystem=m.subsystem
        )
        org_id = dept.organization_id
        if dept.children.exists():
            messages.error(request, "Есть дочерние подразделения — удалите их сначала.")
            return redirect(f"/administration/structure/?org={org_id}")
        if dept.positions.exists():
            messages.error(request, "В подразделении есть должности.")
            return redirect(f"/administration/structure/?org={org_id}")
        name = dept.name
        dept.delete()
        messages.success(request, f"Подразделение «{name}» удалено.")
        return redirect(f"/administration/structure/?org={org_id}")


class PositionCreateView(ModulePermissionMixin, View):
    module_code = "M04"
    required_action = "create"

    def post(self, request):
        m = _ctx_membership(self)
        dept_id = request.POST.get("department")
        dept = get_object_or_404(
            Department, pk=dept_id, organization__subsystem=m.subsystem
        )
        form = PositionForm(request.POST, department=dept)
        if form.is_valid():
            pos = form.save()
            messages.success(request, f"Должность «{pos.name}» добавлена.")
            return redirect(
                f"/administration/structure/?org={dept.organization_id}&open_dept={dept.pk}"
            )
        messages.error(request, "Проверьте поля должности.")
        return redirect(f"/administration/structure/?org={dept.organization_id}")


class PositionModalView(ModulePermissionMixin, View):
    module_code = "M04"

    def get(self, request, pk):
        m = _ctx_membership(self)
        pos = get_object_or_404(
            Position, pk=pk, department__organization__subsystem=m.subsystem
        )
        ctx = position_card_context(pos)
        ctx["can_change"] = user_can(request.user, "M04", "change")
        ctx["can_delete"] = user_can(request.user, "M04", "delete")
        ctx["edit_mode"] = request.GET.get("mode") == "edit"
        if ctx["edit_mode"]:
            ctx["edit_form"] = PositionForm(instance=pos, department=pos.department)
        return render(request, "platform/admin/structure/_position_modal.html", ctx)


class PositionUpdateView(ModulePermissionMixin, View):
    module_code = "M04"
    required_action = "change"

    def post(self, request, pk):
        m = _ctx_membership(self)
        pos = get_object_or_404(
            Position, pk=pk, department__organization__subsystem=m.subsystem
        )
        form = PositionForm(request.POST, instance=pos, department=pos.department)
        if form.is_valid():
            form.save()
            messages.success(request, "Должность сохранена.")
            return redirect(
                f"/administration/structure/?org={pos.department.organization_id}&open_pos={pos.pk}"
            )
        ctx = position_card_context(pos)
        ctx["edit_form"] = form
        ctx["edit_mode"] = True
        ctx["can_change"] = True
        return render(request, "platform/admin/structure/_position_modal.html", ctx)


class PositionDeleteView(ModulePermissionMixin, View):
    module_code = "M04"
    required_action = "delete"

    def post(self, request, pk):
        m = _ctx_membership(self)
        pos = get_object_or_404(
            Position, pk=pk, department__organization__subsystem=m.subsystem
        )
        dept = pos.department
        if UserAssignment.objects.filter(position=pos).exists():
            messages.error(request, "На должность назначены сотрудники.")
            return redirect(f"/administration/structure/?org={dept.organization_id}")
        name = pos.name
        pos.delete()
        messages.success(request, f"Должность «{name}» удалена.")
        return redirect(f"/administration/structure/?org={dept.organization_id}")
