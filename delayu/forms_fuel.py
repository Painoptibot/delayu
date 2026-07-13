"""Формы портала «Топливный пропуск»."""
from decimal import Decimal

from django import forms
from django.db.models import Count

from delayu.models_fuel import FuelApplication, FuelCategory, FuelParityRule
from delayu.services.fuel import normalize_inn, normalize_phone, normalize_plate, validate_inn, validate_plate


class FuelCitizenLoginForm(forms.Form):
    phone = forms.CharField(
        label="Телефон",
        max_length=32,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "+7 (900) 000-00-00",
                "inputmode": "tel",
                "autocomplete": "tel",
            }
        ),
    )
    full_name = forms.CharField(
        label="ФИО",
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "Иванов Иван Иванович",
                "autocomplete": "name",
            }
        ),
    )
    notify_channel = forms.ChoiceField(
        label="Куда отправить код",
        choices=(
            ("sms", "SMS на телефон"),
            ("max", "Мессенджер MAX"),
            ("both", "SMS и MAX"),
        ),
        initial="sms",
        widget=forms.Select(attrs={"class": "fuel-input", "id": "id_notify_channel"}),
    )
    max_chat_id = forms.CharField(
        label="ID чата в MAX",
        max_length=128,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "Например: user_12345",
                "id": "id_max_chat_id",
                "autocomplete": "off",
            }
        ),
    )
    agree_pd = forms.BooleanField(
        label="",
        required=True,
        error_messages={"required": "Необходимо согласие на обработку персональных данных"},
    )

    def clean_phone(self):
        phone = normalize_phone(self.cleaned_data.get("phone", ""))
        if len(phone) < 11:
            raise forms.ValidationError("Укажите корректный номер телефона")
        return phone

    def clean(self):
        cleaned = super().clean()
        channel = cleaned.get("notify_channel", "sms")
        max_id = (cleaned.get("max_chat_id") or "").strip()
        if channel in ("max", "both") and not max_id:
            self.add_error("max_chat_id", "Укажите ID чата MAX для получения кода")
        return cleaned


class FuelCitizenOtpForm(forms.Form):
    code = forms.CharField(
        label="Код подтверждения",
        max_length=6,
        min_length=4,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "000000",
                "inputmode": "numeric",
                "autocomplete": "one-time-code",
                "pattern": "[0-9]*",
            }
        ),
    )


class FuelApplicationForm(forms.Form):
    category = forms.ModelChoiceField(
        label="Категория",
        queryset=FuelCategory.objects.none(),
        empty_label=None,
        widget=forms.Select(attrs={"class": "fuel-input"}),
    )
    plate = forms.CharField(
        label="Госномер",
        max_length=16,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "А123ВС123",
                "style": "text-transform: uppercase",
                "pattern": r"[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}",
                "title": "Формат: А123ВС123",
                "maxlength": "9",
                "autocomplete": "off",
            }
        ),
    )
    vehicle_make = forms.CharField(
        label="Марка и модель",
        max_length=128,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "placeholder": "Lada Vesta / Лада Веста",
                "data-fuel-vehicle-suggest": "1",
                "autocomplete": "off",
            }
        ),
    )
    inn = forms.CharField(
        label="ИНН",
        max_length=12,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input",
                "inputmode": "numeric",
                "data-fuel-dadata": "party",
                "data-fuel-dadata-fill": '{"org_name": "name"}',
                "placeholder": "10 или 12 цифр",
                "pattern": r"\d{10}|\d{12}",
                "title": "ИНН: 10 цифр (организация) или 12 (физлицо/ИП)",
                "maxlength": "12",
                "autocomplete": "off",
            }
        ),
    )
    org_name = forms.CharField(
        label="Организация",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"class": "fuel-input"}),
    )
    agree_rules = forms.BooleanField(
        label="",
        required=True,
        error_messages={"required": "Подтвердите согласие с правилами и обработкой ПДн"},
    )
    preferred_azs = forms.IntegerField(
        label="Предпочтительная АЗС",
        required=False,
        widget=forms.HiddenInput(),
    )
    requested_liters = forms.IntegerField(
        label="Желаемый объём, л",
        required=False,
        min_value=1,
        max_value=500,
        widget=forms.NumberInput(
            attrs={
                "class": "fuel-input",
                "step": "1",
                "placeholder": "Необязательно",
            }
        ),
    )

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            qs = (
                FuelCategory.objects.filter(subsystem=subsystem)
                .annotate(popularity=Count("applications", distinct=True))
                .order_by("-popularity", "sort_order", "code")
            )
            self.fields["category"].queryset = qs
            if not self.is_bound and "category" not in self.initial:
                default_citizen = qs.filter(code="V").first()
                if default_citizen:
                    self.fields["category"].initial = default_citizen.pk

    def clean_plate(self):
        plate = self.cleaned_data.get("plate", "")
        if not validate_plate(plate):
            raise forms.ValidationError("Некорректный формат госномера. Пример: А123ВС123")
        return normalize_plate(plate)

    def clean_inn(self):
        inn = (self.cleaned_data.get("inn") or "").strip()
        if not inn:
            return ""
        inn_n = normalize_inn(inn)
        if not validate_inn(inn_n):
            raise forms.ValidationError("Некорректный ИНН: 10 цифр (юрлицо) или 12 (физлицо/ИП)")
        return inn_n

    def clean_requested_liters(self):
        value = self.cleaned_data.get("requested_liters")
        if value in (None, ""):
            return None
        category = self.cleaned_data.get("category")
        if category and value > category.daily_limit_liters:
            raise forms.ValidationError(
                f"Не больше суточного лимита категории ({category.daily_limit_liters} л)"
            )
        return value


class FuelApplicationStatusFilterForm(forms.Form):
    status = forms.ChoiceField(
        required=False,
        choices=[("", "Все")] + list(FuelApplication.Status.choices),
        widget=forms.Select(attrs={"class": "fuel-input fuel-input--compact"}),
    )


class FuelAzsLoginForm(forms.Form):
    login = forms.CharField(
        label="Логин АЗС",
        max_length=64,
        widget=forms.TextInput(attrs={"class": "fuel-input", "autocomplete": "username"}),
    )
    pin = forms.CharField(
        label="Пароль",
        max_length=16,
        widget=forms.PasswordInput(attrs={"class": "fuel-input", "autocomplete": "current-password"}),
    )


class FuelAzsRedeemForm(forms.Form):
    liters = forms.DecimalField(
        label="Отпущено, л",
        min_value=Decimal("1"),
        max_value=Decimal("500"),
        decimal_places=1,
        widget=forms.NumberInput(attrs={"class": "fuel-input", "step": "0.1"}),
    )
    operator_note = forms.CharField(
        label="Примечание",
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={"class": "fuel-input"}),
    )

    def __init__(self, *args, max_liters=None, **kwargs):
        super().__init__(*args, **kwargs)
        if max_liters is not None:
            cap = Decimal(str(max_liters))
            self.fields["liters"].max_value = cap
            self.fields["liters"].widget.attrs["max"] = str(cap)


class FuelCitizenRedeemReportForm(forms.Form):
    liters = forms.DecimalField(
        label="Фактически заправлено, л",
        min_value=Decimal("0.1"),
        max_value=Decimal("500"),
        decimal_places=1,
        required=False,
        widget=forms.NumberInput(
            attrs={"class": "fuel-input", "step": "0.1", "placeholder": "Необязательно"}
        ),
    )


class FuelAzsManualCodeForm(forms.Form):
    manual_code = forms.CharField(
        label="Код пропуска",
        max_length=8,
        widget=forms.TextInput(
            attrs={
                "class": "fuel-input fuel-manual-code-input",
                "style": "text-transform: uppercase",
                "inputmode": "text",
                "autocomplete": "off",
                "spellcheck": "false",
            }
        ),
    )


class FuelAzsStockForm(forms.Form):
    stock_ai92_liters = forms.IntegerField(
        label="АИ-92, л",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "fuel-input", "placeholder": "0"}),
    )
    stock_ai95_liters = forms.IntegerField(
        label="АИ-95, л",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "fuel-input", "placeholder": "0"}),
    )
    stock_diesel_liters = forms.IntegerField(
        label="Дизель, л",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "fuel-input", "placeholder": "0"}),
    )
    stock_gas_liters = forms.IntegerField(
        label="Газ (СУГ), л",
        min_value=0,
        required=False,
        widget=forms.NumberInput(attrs={"class": "fuel-input", "placeholder": "0"}),
    )
    sells_ai92 = forms.BooleanField(
        label="Продаём АИ-92",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "fuel-check"}),
    )
    sells_ai95 = forms.BooleanField(
        label="Продаём АИ-95",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "fuel-check"}),
    )
    sells_diesel = forms.BooleanField(
        label="Продаём дизель",
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "fuel-check"}),
    )
    sells_gas = forms.BooleanField(
        label="Продаём газ",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "fuel-check"}),
    )
    pump_count = forms.IntegerField(
        label="Рабочих колонок",
        min_value=1,
        max_value=32,
        widget=forms.NumberInput(attrs={"class": "fuel-input"}),
    )
    avg_refuel_minutes = forms.IntegerField(
        label="Среднее время заправки, мин",
        min_value=1,
        max_value=120,
        widget=forms.NumberInput(attrs={"class": "fuel-input"}),
    )
    use_manual_queue = forms.BooleanField(
        label="Указать очередь вручную",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "fuel-check"}),
    )
    queue_minutes = forms.IntegerField(
        label="Очередь, мин",
        min_value=0,
        max_value=999,
        required=False,
        widget=forms.NumberInput(attrs={"class": "fuel-input"}),
    )


class FuelBlacklistAddForm(forms.Form):
    plate = forms.CharField(
        label="Госномер",
        max_length=16,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "style": "text-transform:uppercase",
                "placeholder": "А123ВС123",
                "pattern": r"[АВЕКМНОРСТУХA-Z]\d{3}[АВЕКМНОРСТУХA-Z]{2}\d{2,3}",
                "title": "Формат: А123ВС123",
                "maxlength": "9",
                "autocomplete": "off",
            }
        ),
    )
    inn = forms.CharField(
        label="ИНН",
        max_length=12,
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "10 или 12 цифр",
                "inputmode": "numeric",
                "pattern": r"\d{10}|\d{12}",
                "title": "ИНН: 10 цифр (организация) или 12 (физлицо/ИП)",
                "maxlength": "12",
                "autocomplete": "off",
            }
        ),
    )
    reason = forms.CharField(
        label="Причина",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        cleaned = super().clean()
        plate = (cleaned.get("plate") or "").strip()
        inn = (cleaned.get("inn") or "").strip()
        if not plate and not inn:
            raise forms.ValidationError("Укажите госномер или ИНН")
        if plate:
            if not validate_plate(plate):
                self.add_error(
                    "plate",
                    "Некорректный госномер. Пример: А123ВС123",
                )
            else:
                cleaned["plate"] = normalize_plate(plate)
        if inn:
            inn_n = normalize_inn(inn)
            if not validate_inn(inn_n):
                self.add_error(
                    "inn",
                    "Некорректный ИНН. Нужно 10 цифр (юрлицо) или 12 (физлицо/ИП)",
                )
            else:
                cleaned["inn"] = inn_n
        return cleaned


class FuelParityRuleForm(forms.Form):
    is_enabled = forms.BooleanField(
        label="Ограничение по чётности активно",
        required=False,
    )
    mode = forms.ChoiceField(
        label="Режим",
        choices=FuelParityRule.Mode.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        label="Текст уведомления для жителей",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Оставьте пустым — текст сформируется автоматически по режиму и дате.",
            }
        ),
    )


class FuelParityRuleForm(forms.Form):
    is_enabled = forms.BooleanField(
        label="Ограничение по чётности активно",
        required=False,
    )
    mode = forms.ChoiceField(
        label="Режим",
        choices=FuelParityRule.Mode.choices,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    message = forms.CharField(
        label="Текст уведомления для жителей",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 3,
                "placeholder": "Оставьте пустым — текст сформируется автоматически по режиму и дате.",
            }
        ),
    )


class FuelRejectForm(forms.Form):
    reason = forms.CharField(
        label="Причина отказа",
        max_length=500,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
    )


class FuelAzsStationForm(forms.ModelForm):
    code = forms.CharField(
        label="Код (slug)",
        max_length=32,
        required=False,
        help_text="Пусто — сгенерируется автоматически",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    class Meta:
        from delayu.models_fuel import FuelAzsStation

        model = FuelAzsStation
        fields = [
            "name",
            "network",
            "address",
            "district",
            "latitude",
            "longitude",
            "status",
            "stock_ai92_liters",
            "stock_ai95_liters",
            "stock_diesel_liters",
            "stock_gas_liters",
            "sells_ai92",
            "sells_ai95",
            "sells_diesel",
            "sells_gas",
            "queue_minutes",
            "pump_count",
            "avg_refuel_minutes",
            "use_manual_queue",
            "max_apps_override",
            "fuel_grade",
            "is_accepting_permits",
            "portal_login",
            "portal_pin",
            "portal_blocked",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "network": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.TextInput(attrs={"class": "form-control"}),
            "district": forms.TextInput(attrs={"class": "form-control"}),
            "latitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"class": "form-control", "step": "0.000001"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "stock_ai92_liters": forms.NumberInput(attrs={"class": "form-control"}),
            "stock_ai95_liters": forms.NumberInput(attrs={"class": "form-control"}),
            "stock_diesel_liters": forms.NumberInput(attrs={"class": "form-control"}),
            "stock_gas_liters": forms.NumberInput(attrs={"class": "form-control"}),
            "sells_ai92": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sells_ai95": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sells_diesel": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sells_gas": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "queue_minutes": forms.NumberInput(attrs={"class": "form-control"}),
            "pump_count": forms.NumberInput(attrs={"class": "form-control"}),
            "avg_refuel_minutes": forms.NumberInput(attrs={"class": "form-control"}),
            "use_manual_queue": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "max_apps_override": forms.NumberInput(attrs={"class": "form-control"}),
            "fuel_grade": forms.TextInput(attrs={"class": "form-control"}),
            "is_accepting_permits": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "portal_login": forms.TextInput(attrs={"class": "form-control"}),
            "portal_pin": forms.TextInput(attrs={"class": "form-control"}),
            "portal_blocked": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class FuelPortalSettingsForm(forms.ModelForm):
    class Meta:
        from delayu.models_fuel import FuelPortalSettings

        model = FuelPortalSettings
        fields = ["permit_quota_liters", "auto_queue_enabled"]
        widgets = {
            "permit_quota_liters": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 200}),
            "auto_queue_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class FuelSupportTicketForm(forms.Form):
    operator_note = forms.CharField(
        label="Ответ оператора",
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )
    status = forms.ChoiceField(
        label="Статус",
        choices=[
            ("new", "Новое"),
            ("in_progress", "В работе"),
            ("answered", "Отвечено"),
            ("closed", "Закрыто"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
