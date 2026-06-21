"""Многошаговые мастера создания сущностей УЖВ."""
from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.widgets_dadata import DadataSnilsInput, DadataTextarea, DadataTextInput
from delayu.models_uzhv import HousingCitizen, HousingQueueCase
from delayu.forms_uzhv import _assignee_qs

User = get_user_model()


class UzhvChainWizardForm(BootstrapFormMixin, forms.Form):
    """Цепочка: гражданин → (опц.) дело → (опц.) обращение."""

    MODE_NEW = "new"
    MODE_EXISTING = "existing"

    citizen_mode = forms.ChoiceField(
        label="Гражданин",
        choices=[
            (MODE_NEW, "Новый гражданин"),
            (MODE_EXISTING, "Выбрать из реестра"),
        ],
        initial=MODE_NEW,
        widget=forms.RadioSelect(attrs={"class": "form-check-input uzhv-chain-mode"}),
    )
    existing_citizen = forms.ModelChoiceField(
        label="Гражданин из реестра",
        queryset=HousingCitizen.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    last_name = forms.CharField(
        label="Фамилия",
        max_length=120,
        required=False,
        widget=DadataTextInput(
            dadata_type="fio",
            dadata_parts="SURNAME",
            dadata_fill={"first_name": "name", "middle_name": "patronymic"},
        ),
    )
    first_name = forms.CharField(
        label="Имя",
        max_length=120,
        required=False,
        widget=DadataTextInput(dadata_type="fio", dadata_parts="NAME"),
    )
    middle_name = forms.CharField(
        label="Отчество",
        max_length=120,
        required=False,
        widget=DadataTextInput(dadata_type="fio", dadata_parts="PATRONYMIC"),
    )
    snils = forms.CharField(
        label="СНИЛС",
        max_length=32,
        required=False,
        widget=DadataSnilsInput(),
    )
    phone = forms.CharField(
        label="Телефон",
        max_length=32,
        required=False,
        widget=DadataTextInput(dadata_type="phone"),
    )
    reg_address = forms.CharField(
        label="Адрес регистрации",
        required=False,
        widget=DadataTextarea(dadata_type="address", rows=2),
    )

    create_case = forms.BooleanField(
        label="Создать учётное дело",
        required=False,
        initial=True,
    )
    case_category = forms.ChoiceField(
        label="Категория учёта",
        choices=HousingQueueCase.Category.choices,
        initial=HousingQueueCase.Category.GENERAL,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    case_status = forms.ChoiceField(
        label="Статус дела",
        choices=HousingQueueCase.Status.choices,
        initial=HousingQueueCase.Status.REGISTERED,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    case_assignee = forms.ModelChoiceField(
        label="Исполнитель по делу",
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )

    create_appeal = forms.BooleanField(
        label="Зарегистрировать обращение",
        required=False,
        initial=False,
    )
    appeal_subject = forms.CharField(
        label="Тема обращения",
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
    )
    appeal_body = forms.CharField(
        label="Содержание",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
    )
    appeal_assignee = forms.ModelChoiceField(
        label="Исполнитель по обращению",
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    received_at = forms.DateField(
        label="Дата поступления",
        widget=DatePickerInput(),
        required=False,
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            qs = HousingCitizen.objects.filter(subsystem=subsystem).order_by(
                "last_name", "first_name"
            )
            self.fields["existing_citizen"].queryset = qs
            assignees = _assignee_qs(subsystem)
            self.fields["case_assignee"].queryset = assignees
            self.fields["appeal_assignee"].queryset = assignees

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("citizen_mode")
        if mode == self.MODE_EXISTING:
            if not cleaned.get("existing_citizen"):
                self.add_error("existing_citizen", "Выберите гражданина")
        else:
            if not (cleaned.get("last_name") or "").strip():
                self.add_error("last_name", "Укажите фамилию")
            if not (cleaned.get("first_name") or "").strip():
                self.add_error("first_name", "Укажите имя")
        if cleaned.get("create_appeal"):
            if not (cleaned.get("appeal_subject") or "").strip():
                self.add_error("appeal_subject", "Укажите тему обращения")
            if not cleaned.get("received_at"):
                self.add_error("received_at", "Укажите дату поступления")
        return cleaned
