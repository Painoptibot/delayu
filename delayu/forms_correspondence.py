from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.models import CaseFile, Correspondence, PrintTemplate

User = get_user_model()


class InboundRegisterForm(BootstrapFormMixin, forms.Form):
    subject = forms.CharField(label="Тема", max_length=500)
    counterparty = forms.CharField(label="Отправитель", max_length=255)
    reg_date = forms.DateField(
        label="Дата регистрации",
        widget=DatePickerInput(),
    )
    assignee = forms.ModelChoiceField(
        label="Исполнитель",
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    create_case = forms.BooleanField(
        label="Создать новое дело",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "id": "id_create_case"}),
    )
    new_case_title = forms.CharField(
        label="Название нового дела",
        max_length=500,
        required=False,
        widget=forms.TextInput(
            attrs={"class": BOOTSTRAP, "placeholder": "По умолчанию — тема обращения"}
        ),
    )
    status = forms.ChoiceField(
        label="Статус",
        choices=Correspondence.Status.choices,
        initial=Correspondence.Status.REGISTERED,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            users = User.objects.filter(subsystem_memberships__subsystem=subsystem).distinct()
            self.fields["assignee"].queryset = users
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
        from delayu.services.nsi_choices import apply_field

        apply_field(
            self, "status", subsystem, "correspondence_status", Correspondence.Status.choices
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("create_case") and cleaned.get("case"):
            self.add_error("case", "Выберите существующее дело или отметьте создание нового.")
        if cleaned.get("create_case") and not cleaned.get("new_case_title"):
            cleaned["new_case_title"] = cleaned.get("subject", "")
        return cleaned


class OutboundRegisterForm(InboundRegisterForm):
    linked_incoming = forms.ModelChoiceField(
        label="В ответ на входящее",
        queryset=Correspondence.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, subsystem=subsystem, **kwargs)
        self.fields.pop("create_case", None)
        self.fields.pop("new_case_title", None)
        if subsystem:
            self.fields["linked_incoming"].queryset = Correspondence.objects.filter(
                subsystem=subsystem, direction=Correspondence.Direction.IN
            ).order_by("-reg_date")


class CorrespondenceRouteForm(BootstrapFormMixin, forms.Form):
    to_user = forms.ModelChoiceField(
        label="Кому",
        queryset=User.objects.none(),
        widget=forms.Select(attrs={"class": SELECT}),
    )
    comment = forms.CharField(
        label="Резолюция / комментарий",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["to_user"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()


class PrintTemplateForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrintTemplate
        fields = ["code", "name", "body", "is_active"]
        widgets = {"body": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 10})}


class ScanBatchForm(BootstrapFormMixin, forms.Form):
    case = forms.ModelChoiceField(
        label="Дело",
        queryset=CaseFile.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    correspondence = forms.ModelChoiceField(
        label="Корреспонденция",
        queryset=Correspondence.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["case"].queryset = CaseFile.objects.filter(
                subsystem=subsystem, is_archived=False
            )
            self.fields["correspondence"].queryset = Correspondence.objects.filter(
                subsystem=subsystem
            ).order_by("-reg_date")[:100]
