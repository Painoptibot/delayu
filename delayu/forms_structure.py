from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import Organization
from delayu.models_business import Department, Position, UserAssignment

User = get_user_model()


class DepartmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Department
        fields = ["code", "name", "parent", "manager"]
        widgets = {
            "parent": forms.Select(attrs={"class": SELECT}),
            "manager": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, organization=None, department_pk=None, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        if organization:
            qs = Department.objects.filter(organization=organization)
            if department_pk:
                qs = qs.exclude(pk=department_pk)
            self.fields["parent"].queryset = qs
            self.fields["parent"].required = False
            members = User.objects.filter(
                subsystem_memberships__organization=organization
            ).distinct()
            self.fields["manager"].queryset = members
            self.fields["manager"].required = False

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        qs = Department.objects.filter(organization=self.organization, code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Подразделение с таким кодом уже существует.")
        return code

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if commit:
            obj.save()
        return obj


class PositionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Position
        fields = ["code", "name", "headcount"]

    def __init__(self, *args, department=None, **kwargs):
        self.department = department
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        qs = Position.objects.filter(department=self.department, code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Должность с таким кодом уже есть в подразделении.")
        return code

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.department = self.department
        if commit:
            obj.save()
        return obj


class UserAssignmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = UserAssignment
        fields = ["user", "position"]

    def __init__(self, *args, department=None, **kwargs):
        self.department = department
        super().__init__(*args, **kwargs)
        if department:
            self.fields["position"].queryset = Position.objects.filter(department=department)
            org = department.organization
            self.fields["user"].queryset = User.objects.filter(
                subsystem_memberships__organization=org
            ).distinct()
