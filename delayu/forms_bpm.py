import json

from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import BPMTemplate, CaseFile, CaseRegulation, SLARule

User = get_user_model()


class BPMTemplateForm(BootstrapFormMixin, forms.ModelForm):
    steps_json = forms.CharField(
        label="Шаги (JSON)",
        widget=forms.Textarea(
            attrs={
                "class": BOOTSTRAP,
                "rows": 8,
                "placeholder": '[{"id":"s1","name":"Специалист","assignee_id":1}]',
            }
        ),
        help_text="Массив шагов: id, name, assignee_id",
    )

    class Meta:
        model = BPMTemplate
        fields = ["code", "name", "description", "is_active"]

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        if instance and instance.steps:
            self.fields["steps_json"].initial = json.dumps(instance.steps, ensure_ascii=False, indent=2)

    def clean_steps_json(self):
        raw = self.cleaned_data.get("steps_json", "").strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise forms.ValidationError(f"Некорректный JSON: {e}") from e
        if not isinstance(data, list):
            raise forms.ValidationError("Ожидается JSON-массив шагов.")
        return data

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.steps = self.cleaned_data["steps_json"]
        if commit:
            obj.save()
        return obj


class BPMStartForm(BootstrapFormMixin, forms.Form):
    template = forms.ModelChoiceField(
        label="Шаблон процесса",
        queryset=BPMTemplate.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["template"].queryset = BPMTemplate.objects.filter(
                subsystem=subsystem, is_active=True
            )
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )


class BPMTaskDecisionForm(BootstrapFormMixin, forms.Form):
    comment = forms.CharField(
        label="Комментарий",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3}),
    )


class SLARuleForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SLARule
        fields = ["code", "name", "case_kind", "hours_limit", "is_active", "escalate_to"]
        widgets = {"escalate_to": forms.Select(attrs={"class": SELECT})}

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["escalate_to"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()


class CaseRegulationForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CaseRegulation
        fields = [
            "code",
            "name",
            "default_working_days",
            "applies_on_status",
            "notes",
            "is_active",
        ]
        widgets = {"applies_on_status": forms.Select(attrs={"class": SELECT})}
