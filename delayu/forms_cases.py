from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.models import CaseFile

User = get_user_model()


class CaseFileForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CaseFile
        fields = ["title", "description", "assignee", "due_date", "priority", "status"]
        widgets = {
            "due_date": DatePickerInput(),
            "description": forms.Textarea(attrs={"rows": 4, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
            "priority": forms.NumberInput(attrs={"class": BOOTSTRAP, "min": 1, "max": 3}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.services.nsi_choices import apply_field

        apply_field(self, "status", subsystem, "case_status", CaseFile.Status.choices)
        if subsystem:
            self.fields["assignee"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct().order_by("username")
            self.fields["assignee"].required = False


class CaseWizardForm(BootstrapFormMixin, forms.Form):
    title = forms.CharField(label="Тема дела", max_length=500)
    description = forms.CharField(
        label="Описание",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3}),
    )
    assignee = forms.ModelChoiceField(
        label="Исполнитель",
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    due_date = forms.DateField(
        label="Контрольный срок",
        required=False,
        widget=DatePickerInput(),
    )
    priority = forms.IntegerField(
        label="Приоритет (1–3)",
        min_value=1,
        max_value=3,
        initial=2,
        widget=forms.NumberInput(attrs={"class": BOOTSTRAP}),
    )
    status = forms.ChoiceField(
        label="Статус",
        choices=CaseFile.Status.choices,
        initial=CaseFile.Status.NEW,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.services.nsi_choices import apply_field

        apply_field(self, "status", subsystem, "case_status", CaseFile.Status.choices)
        apply_field(
            self,
            "priority",
            subsystem,
            "case_priority",
            [(1, "1"), (2, "2"), (3, "3")],
            cast=int,
        )
        if subsystem:
            self.fields["assignee"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct().order_by("username")
