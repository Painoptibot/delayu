from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import Organization, Role
from delayu.models_business import UserProfile

User = get_user_model()

PROFILE_FIELDS = [
    "middle_name",
    "gender",
    "birth_date",
    "snils",
    "inn",
    "passport_series",
    "passport_number",
    "passport_issued_by",
    "passport_issued_date",
    "phone",
    "phone_mobile",
    "phone_work",
    "phone_internal",
    "email_personal",
    "telegram",
    "telegram_chat_id",
    "address_registration",
    "address_residence",
    "employee_number",
    "tab_number",
    "position_title",
    "employment_type",
    "hire_date",
    "dismissal_date",
    "department_text",
    "manager_name",
    "timezone",
    "locale",
    "comment",
    "must_change_password",
    "two_factor_enabled",
]


class UserWizardForm(BootstrapFormMixin, forms.Form):
    """Единая форма мастера создания пользователя (4 шага в UI)."""

    username = forms.CharField(label="Логин", max_length=150)
    email = forms.EmailField(label="E-mail (рабочий)", required=False)
    password1 = forms.CharField(label="Пароль", widget=forms.PasswordInput(attrs={"class": BOOTSTRAP}))
    password2 = forms.CharField(label="Повтор пароля", widget=forms.PasswordInput(attrs={"class": BOOTSTRAP}))
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    organization = forms.ModelChoiceField(label="Организация", queryset=Organization.objects.none())
    role = forms.ModelChoiceField(label="Роль", queryset=Role.objects.none())

    def __init__(self, *args, subsystem=None, **kwargs):
        self.subsystem = subsystem
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["organization"].queryset = Organization.objects.filter(subsystem=subsystem)
            self.fields["role"].queryset = Role.objects.filter(subsystem=subsystem)
        for name in PROFILE_FIELDS:
            model_field = UserProfile._meta.get_field(name)
            form_field = model_field.formfield()
            if form_field:
                if isinstance(form_field.widget, forms.CheckboxInput):
                    form_field.widget.attrs.setdefault("class", "form-check-input")
                elif isinstance(form_field.widget, forms.Select):
                    form_field.widget.attrs.setdefault("class", SELECT)
                elif isinstance(form_field.widget, forms.Textarea):
                    form_field.widget.attrs.setdefault("class", BOOTSTRAP)
                else:
                    form_field.widget.attrs.setdefault("class", BOOTSTRAP)
                self.fields[name] = form_field

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("Пользователь с таким логином уже существует.")
        return username

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 != p2:
            self.add_error("password2", "Пароли не совпадают.")
        elif p1:
            validate_password(p1)
        return cleaned

    def save(self):
        from delayu.services.users import create_user_with_membership

        return create_user_with_membership(
            subsystem=self.subsystem,
            username=self.cleaned_data["username"],
            email=self.cleaned_data.get("email") or "",
            password=self.cleaned_data["password1"],
            first_name=self.cleaned_data.get("first_name") or "",
            last_name=self.cleaned_data.get("last_name") or "",
            organization=self.cleaned_data["organization"],
            role=self.cleaned_data["role"],
            profile_data={k: self.cleaned_data.get(k) for k in PROFILE_FIELDS},
        )


class UserEditForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(label="E-mail (рабочий)", required=False)
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    is_active = forms.BooleanField(label="Активен", required=False)
    organization = forms.ModelChoiceField(label="Организация", queryset=Organization.objects.none())
    role = forms.ModelChoiceField(label="Роль", queryset=Role.objects.none())
    new_password = forms.CharField(
        label="Новый пароль",
        required=False,
        widget=forms.PasswordInput(attrs={"class": BOOTSTRAP}),
    )

    def __init__(self, *args, user=None, membership=None, subsystem=None, **kwargs):
        self.user = user
        self.membership = membership
        self.subsystem = subsystem
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["organization"].queryset = Organization.objects.filter(subsystem=subsystem)
            self.fields["role"].queryset = Role.objects.filter(subsystem=subsystem)
        profile, _ = UserProfile.objects.get_or_create(user=user)
        if user:
            self.fields["email"].initial = user.email
            self.fields["first_name"].initial = user.first_name
            self.fields["last_name"].initial = user.last_name
            self.fields["is_active"].initial = user.is_active
        if membership:
            self.fields["organization"].initial = membership.organization_id
            self.fields["role"].initial = membership.role_id
        for name in PROFILE_FIELDS:
            model_field = UserProfile._meta.get_field(name)
            form_field = model_field.formfield()
            if form_field:
                if isinstance(form_field.widget, forms.CheckboxInput):
                    form_field.widget.attrs.setdefault("class", "form-check-input")
                elif isinstance(form_field.widget, forms.Select):
                    form_field.widget.attrs.setdefault("class", SELECT)
                else:
                    form_field.widget.attrs.setdefault("class", BOOTSTRAP)
                form_field.initial = getattr(profile, name, None)
                self.fields[name] = form_field

    def clean_new_password(self):
        pwd = self.cleaned_data.get("new_password")
        if pwd:
            validate_password(pwd, user=self.user)
        return pwd

    def save(self):
        from delayu.services.users import update_user_membership

        data = dict(self.cleaned_data)
        pwd = data.pop("new_password", None) or None
        org = data.pop("organization")
        role = data.pop("role")
        profile_data = {k: data.pop(k, None) for k in PROFILE_FIELDS if k in data}
        user_fields = {
            "email": data.get("email") or "",
            "first_name": data.get("first_name") or "",
            "last_name": data.get("last_name") or "",
            "is_active": data.get("is_active", False),
        }
        return update_user_membership(
            user=self.user,
            membership=self.membership,
            user_fields=user_fields,
            password=pwd or None,
            organization=org,
            role=role,
            profile_data=profile_data,
        )
