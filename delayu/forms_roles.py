from django import forms
from django.core.exceptions import ValidationError

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models import Role
from delayu.services.roles import PERM_ACTIONS, enabled_modules_for_subsystem, save_role_permissions


class RoleBaseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Role
        fields = ["code", "name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, subsystem=None, **kwargs):
        self.subsystem = subsystem
        super().__init__(*args, **kwargs)
        self._add_permission_fields()

    def _add_permission_fields(self):
        if not self.subsystem:
            return
        for mod in enabled_modules_for_subsystem(self.subsystem):
            for action in PERM_ACTIONS:
                self.fields[f"perm_{mod.code}_{action}"] = forms.BooleanField(
                    label=f"{mod.code} — {action}",
                    required=False,
                    widget=forms.CheckboxInput(attrs={"class": "form-check-input perm-checkbox"}),
                )

    def _permissions_from_cleaned(self):
        modules = {m.code: m for m in enabled_modules_for_subsystem(self.subsystem)}
        return {
            module: {
                action: self.cleaned_data.get(f"perm_{mod_code}_{action}", False)
                for action in PERM_ACTIONS
            }
            for mod_code, module in modules.items()
        }


class RoleWizardForm(RoleBaseForm):
    """Шаг 1: реквизиты; шаг 2 — матрица в шаблоне."""

    def clean_code(self):
        code = self.cleaned_data["code"].strip().lower()
        qs = Role.objects.filter(subsystem=self.subsystem, code__iexact=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Роль с таким кодом уже есть в подсистеме.")
        return code

    def save(self, commit=True):
        role = super().save(commit=False)
        role.subsystem = self.subsystem
        if commit:
            role.save()
            save_role_permissions(role, self.subsystem, self._permissions_from_cleaned())
        return role


class RoleEditForm(RoleBaseForm):
    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, subsystem=subsystem, **kwargs)
        if self.instance.pk and self.subsystem:
            from delayu.services.roles import permissions_to_form_initial

            for key, val in permissions_to_form_initial(self.instance, self.subsystem).items():
                if key in self.fields:
                    self.fields[key].initial = val

    def clean_code(self):
        code = self.cleaned_data["code"].strip().lower()
        qs = Role.objects.filter(subsystem=self.subsystem, code__iexact=code).exclude(
            pk=self.instance.pk
        )
        if qs.exists():
            raise ValidationError("Роль с таким кодом уже есть.")
        return code

    def save(self, commit=True):
        role = super().save(commit=commit)
        if commit and self.subsystem:
            save_role_permissions(role, self.subsystem, self._permissions_from_cleaned())
        return role


class RoleCopyForm(BootstrapFormMixin, forms.Form):
    code = forms.CharField(label="Код новой роли", max_length=64)
    name = forms.CharField(label="Наименование", max_length=128)
