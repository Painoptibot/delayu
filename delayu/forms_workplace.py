from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.models import Favorite, SavedFilter
from delayu.models_business import UserProfile

User = get_user_model()


class CabinetPrefsForm(BootstrapFormMixin, forms.Form):
    timezone = forms.CharField(label="Часовой пояс", max_length=64)
    locale = forms.CharField(label="Язык", max_length=8)
    email_personal = forms.EmailField(label="Личный e-mail", required=False)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)


class CabinetProfileForm(BootstrapFormMixin, forms.Form):
    """Редактирование учётной записи и профиля в личном кабинете."""

    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    email = forms.EmailField(label="Рабочий e-mail", required=False)
    middle_name = forms.CharField(label="Отчество", max_length=150, required=False)
    phone = forms.CharField(label="Телефон основной", max_length=32, required=False)
    phone_mobile = forms.CharField(label="Мобильный", max_length=32, required=False)
    phone_work = forms.CharField(label="Рабочий телефон", max_length=32, required=False)
    phone_internal = forms.CharField(label="Внутренний", max_length=16, required=False)
    email_personal = forms.EmailField(label="Личный e-mail", required=False)
    telegram = forms.CharField(label="Telegram (@username)", max_length=64, required=False)
    telegram_chat_id = forms.CharField(
        label="Telegram chat_id",
        max_length=32,
        required=False,
        help_text="Числовой ID из @userinfobot — надёжнее для бота",
    )
    position_title = forms.CharField(label="Должность", max_length=255, required=False)
    employee_number = forms.CharField(label="Табельный №", max_length=32, required=False)
    department_text = forms.CharField(label="Подразделение", max_length=255, required=False)
    manager_name = forms.CharField(label="Руководитель", max_length=255, required=False)
    gender = forms.ChoiceField(
        label="Пол",
        choices=UserProfile.Gender.choices,
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    birth_date = forms.DateField(label="Дата рождения", required=False, widget=DatePickerInput())
    hire_date = forms.DateField(label="Дата приёма", required=False, widget=DatePickerInput())
    dismissal_date = forms.DateField(label="Дата увольнения", required=False, widget=DatePickerInput())
    snils = forms.CharField(label="СНИЛС", max_length=14, required=False)
    inn = forms.CharField(label="ИНН", max_length=12, required=False)
    passport_series = forms.CharField(label="Серия паспорта", max_length=8, required=False)
    passport_number = forms.CharField(label="Номер паспорта", max_length=16, required=False)
    passport_issued_by = forms.CharField(label="Кем выдан", max_length=255, required=False)
    passport_issued_date = forms.DateField(label="Дата выдачи паспорта", required=False, widget=DatePickerInput())
    address_registration = forms.CharField(label="Адрес регистрации", max_length=500, required=False)
    address_residence = forms.CharField(label="Адрес проживания", max_length=500, required=False)
    tab_number = forms.CharField(label="Табельный номер", max_length=32, required=False)
    employment_type = forms.ChoiceField(
        label="Тип занятости",
        choices=UserProfile.EmploymentType.choices,
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    timezone = forms.ChoiceField(
        label="Часовой пояс",
        choices=[("Europe/Moscow", "Москва (UTC+3)")],
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    locale = forms.ChoiceField(
        label="Язык интерфейса",
        choices=[("ru", "Русский"), ("en", "English")],
        required=False,
        widget=forms.Select(attrs={"class": SELECT}),
    )
    comment = forms.CharField(
        label="Примечание",
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 2}),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        from delayu.services.nsi_choices import apply_field

        apply_field(self, "gender", subsystem, "gender", UserProfile.Gender.choices)
        apply_field(
            self,
            "employment_type",
            subsystem,
            "employment_type",
            UserProfile.EmploymentType.choices,
        )
        apply_field(self, "timezone", subsystem, "timezone", [("Europe/Moscow", "Москва")])
        apply_field(self, "locale", subsystem, "locale", [("ru", "Русский"), ("en", "English")])
        pii_fields = (
            "first_name",
            "last_name",
            "middle_name",
            "email",
            "phone",
            "phone_mobile",
            "phone_work",
            "phone_internal",
            "email_personal",
            "telegram",
            "telegram_chat_id",
            "position_title",
            "employee_number",
            "department_text",
            "manager_name",
            "snils",
            "inn",
            "passport_series",
            "passport_number",
            "passport_issued_by",
            "address_registration",
            "address_residence",
            "tab_number",
            "comment",
        )
        for fname in pii_fields:
            if fname in self.fields:
                self.fields[fname].widget.attrs["data-pii"] = "1"

    def save(self, user):
        profile, _ = UserProfile.objects.get_or_create(user=user)
        user.first_name = self.cleaned_data["first_name"]
        user.last_name = self.cleaned_data["last_name"]
        user.email = self.cleaned_data["email"]
        user.save(update_fields=["first_name", "last_name", "email"])
        for field in (
            "middle_name",
            "phone",
            "phone_mobile",
            "phone_work",
            "phone_internal",
            "email_personal",
            "telegram",
            "telegram_chat_id",
            "position_title",
            "employee_number",
            "department_text",
            "manager_name",
            "gender",
            "birth_date",
            "hire_date",
            "dismissal_date",
            "snils",
            "inn",
            "passport_series",
            "passport_number",
            "passport_issued_by",
            "passport_issued_date",
            "address_registration",
            "address_residence",
            "tab_number",
            "employment_type",
            "timezone",
            "locale",
            "comment",
        ):
            val = self.cleaned_data.get(field)
            if val is None:
                continue
            if val == "" and field.endswith("_date"):
                setattr(profile, field, None)
            else:
                setattr(profile, field, val)
        profile.save()
        return profile

    @classmethod
    def initial_from_user(cls, user, profile):
        return {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "middle_name": profile.middle_name,
            "phone": profile.phone,
            "phone_mobile": profile.phone_mobile,
            "phone_work": profile.phone_work,
            "phone_internal": profile.phone_internal,
            "email_personal": profile.email_personal,
            "telegram": profile.telegram,
            "telegram_chat_id": profile.telegram_chat_id,
            "position_title": profile.position_title,
            "employee_number": profile.employee_number,
            "department_text": profile.department_text,
            "manager_name": profile.manager_name,
            "gender": profile.gender,
            "birth_date": profile.birth_date,
            "hire_date": profile.hire_date,
            "dismissal_date": profile.dismissal_date,
            "snils": profile.snils,
            "inn": profile.inn,
            "passport_series": profile.passport_series,
            "passport_number": profile.passport_number,
            "passport_issued_by": profile.passport_issued_by,
            "passport_issued_date": profile.passport_issued_date,
            "address_registration": profile.address_registration,
            "address_residence": profile.address_residence,
            "tab_number": profile.tab_number,
            "employment_type": profile.employment_type,
            "timezone": profile.timezone,
            "locale": profile.locale,
            "comment": profile.comment,
        }


class FavoriteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Favorite
        fields = ["label", "url_path", "icon_class", "sort_order"]
        widgets = {"sort_order": forms.NumberInput(attrs={"class": BOOTSTRAP, "min": 0})}


class SavedFilterForm(BootstrapFormMixin, forms.Form):
    module_code = forms.ChoiceField(
        label="Модуль",
        choices=[
            ("M22", "M22 — Дела"),
            ("M05", "M05 — Документы"),
            ("M24", "M24 — Входящие"),
            ("M08", "M08 — На сегодня"),
        ],
        widget=forms.Select(attrs={"class": SELECT}),
    )
    name = forms.CharField(label="Название фильтра", max_length=128)
    params_json = forms.CharField(
        label="Параметры (JSON)",
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3}),
        initial="{}",
    )
