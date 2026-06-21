from django import forms
from django.core.exceptions import ValidationError

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models import ModuleCatalog, Subsystem
from delayu.services.subsystems import save_module_matrix


class SubsystemWizardForm(BootstrapFormMixin, forms.ModelForm):
    module_codes = forms.MultipleChoiceField(
        label="Включённые модули",
        required=False,
        widget=forms.MultipleHiddenInput,
    )
    publish_now = forms.BooleanField(
        label="Опубликовать сразу (статус «Действует»)",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    config_version = forms.CharField(
        label="Метка версии",
        max_length=32,
        required=False,
        widget=forms.TextInput(attrs={"class": BOOTSTRAP, "placeholder": "например 1.0.0"}),
    )

    class Meta:
        model = Subsystem
        fields = [
            "code",
            "name",
            "description",
            "industry_template",
            "primary_color",
            "status",
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "code": forms.TextInput(attrs={"class": BOOTSTRAP}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (m.code, f"{m.code} — {m.name}")
            for m in ModuleCatalog.objects.filter(is_active=True).order_by("sort_order")
        ]
        self.fields["module_codes"].choices = choices
        if not self.instance.pk:
            self.fields["status"].initial = Subsystem.Status.DRAFT
            core_codes = list(
                ModuleCatalog.objects.filter(is_active=True, is_core=True).values_list(
                    "code", flat=True
                )
            )
            self.fields["module_codes"].initial = core_codes or [c[0] for c in choices[:6]]

    def clean_code(self):
        code = self.cleaned_data["code"].strip().lower()
        if Subsystem.objects.filter(code__iexact=code).exists():
            raise ValidationError("Код подсистемы уже занят.")
        return code

    def save(self, creator_user=None):
        publish = self.cleaned_data.pop("publish_now", False)
        version = self.cleaned_data.pop("config_version", "")
        module_codes = self.cleaned_data.pop("module_codes", [])
        subsystem = super().save(commit=False)
        if publish:
            subsystem.status = Subsystem.Status.ACTIVE
        subsystem.save()
        from delayu.services.subsystems import provision_subsystem, publish_subsystem

        provision_subsystem(subsystem, module_codes, creator_user)
        if publish:
            publish_subsystem(subsystem, version)
        elif version:
            subsystem.config_version = version
            subsystem.save(update_fields=["config_version"])
        return subsystem


class SubsystemEditForm(BootstrapFormMixin, forms.ModelForm):
    module_codes = forms.MultipleChoiceField(required=False, widget=forms.MultipleHiddenInput)

    class Meta:
        model = Subsystem
        fields = [
            "code",
            "name",
            "description",
            "industry_template",
            "primary_color",
            "status",
            "config_version",
        ]
        widgets = {
            "primary_color": forms.TextInput(attrs={"type": "color"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [
            (m.code, m.code)
            for m in ModuleCatalog.objects.filter(is_active=True).order_by("sort_order")
        ]
        self.fields["module_codes"].choices = choices
        if self.instance.pk:
            self.fields["module_codes"].initial = list(
                self.instance.module_links.filter(enabled=True).values_list(
                    "module__code", flat=True
                )
            )

    def save(self, commit=True):
        subsystem = super().save(commit=commit)
        if commit:
            save_module_matrix(subsystem, self.cleaned_data.get("module_codes"))
        return subsystem


class SubsystemCloneForm(BootstrapFormMixin, forms.Form):
    code = forms.SlugField(label="Код новой подсистемы", max_length=64)
    name = forms.CharField(label="Наименование", max_length=255)
