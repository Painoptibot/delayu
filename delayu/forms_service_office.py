"""Формы календаря, сценариев, воронок, рассылок, рекламы, счетов и медиатеки."""
from django import forms

from delayu.forms_service import _controls
from delayu.models_service import (
    ServiceAd,
    ServiceCalendar,
    ServiceCustomer,
    ServiceDeal,
    ServiceFunnel,
    ServiceInvoice,
    ServiceMedia,
    ServiceWorkflow,
)


class CalendarForm(forms.Form):
    name = forms.CharField(label="Календарь", max_length=255)
    kind = forms.ChoiceField(label="Тип", choices=ServiceCalendar.Kind.choices)
    minutes = forms.IntegerField(label="Минут", min_value=5, max_value=480, initial=30)
    owner_name = forms.CharField(label="Ведущий", max_length=128, required=False)
    active = forms.BooleanField(label="Принимает записи", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class AppointmentForm(forms.Form):
    calendar = forms.ModelChoiceField(label="Календарь", queryset=ServiceCalendar.objects.none())
    customer = forms.ModelChoiceField(label="Заказчик", queryset=ServiceCustomer.objects.none())
    starts_at = forms.DateTimeField(
        label="Начало",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"],
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}),
    )
    note = forms.CharField(label="Заметка", max_length=255, required=False)

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem is not None:
            self.fields["calendar"].queryset = ServiceCalendar.objects.filter(subsystem=subsystem, active=True)
            self.fields["customer"].queryset = ServiceCustomer.objects.filter(subsystem=subsystem)
        _controls(self)


class WorkflowForm(forms.Form):
    name = forms.CharField(label="Сценарий", max_length=255)
    folder = forms.CharField(label="Папка", max_length=128, initial="General Automations")
    trigger = forms.ChoiceField(
        label="Событие",
        choices=[
            ("deal_created", "Сделка создана"),
            ("stage_changed", "Стадия изменилась"),
            ("deal_ready", "Заявка заполнена"),
            ("manual", "Снимок аккаунта"),
        ],
    )
    action = forms.ChoiceField(
        label="Действие",
        choices=[
            ("first_response", "SMS о стадии через час"),
            ("announce_stage", "SMS при смене стадии"),
            ("qualify", "Квалификация"),
            ("catalog", "Письмо с каталогом"),
            ("church", "Церковное письмо"),
            ("province", "Дожим по провинции"),
            ("stored", "Снимок, сам не запускается"),
        ],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class FunnelForm(forms.Form):
    name = forms.CharField(label="Воронка", max_length=255)
    steps = forms.CharField(label="Шаги", widget=forms.Textarea(attrs={"rows": 4}))
    status = forms.ChoiceField(
        label="Статус", choices=ServiceFunnel.Status.choices, initial=ServiceFunnel.Status.ACTIVE
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class MailingForm(forms.Form):
    subject = forms.CharField(label="Тема", max_length=255)
    audience = forms.CharField(
        label="Метка аудитории", max_length=64, required=False, help_text="Пусто — все заказчики"
    )
    body = forms.CharField(label="Письмо", widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class AdForm(forms.Form):
    name = forms.CharField(label="Кампания", max_length=255)
    network = forms.ChoiceField(label="Сеть", choices=ServiceAd.Network.choices)
    province = forms.CharField(label="Провинция", max_length=8, required=False)
    job_type = forms.ChoiceField(label="Задача", choices=ServiceCustomer.JobType.choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class AdLeadForm(forms.Form):
    ad = forms.ModelChoiceField(label="Кампания", queryset=ServiceAd.objects.none())
    display_name = forms.CharField(label="Имя", max_length=255)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem is not None:
            self.fields["ad"].queryset = ServiceAd.objects.filter(subsystem=subsystem, active=True)
        _controls(self)


class InvoiceForm(forms.Form):
    customer = forms.ModelChoiceField(label="Заказчик", queryset=ServiceCustomer.objects.none())
    title = forms.CharField(label="Счёт", max_length=255)
    amount = forms.DecimalField(label="Сумма, C$", min_value=0, decimal_places=2, max_digits=12)
    status = forms.ChoiceField(label="Статус", choices=ServiceInvoice.Status.choices)

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem is not None:
            self.fields["customer"].queryset = ServiceCustomer.objects.filter(subsystem=subsystem)
        _controls(self)


class MediaForm(forms.Form):
    folder = forms.CharField(label="Папка", max_length=128, required=False)
    title = forms.CharField(label="Название", max_length=255)
    kind = forms.ChoiceField(label="Тип", choices=ServiceMedia.Kind.choices)
    file = forms.FileField(label="Файл", required=False)
    note = forms.CharField(label="Заметка", max_length=255, required=False)

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem is not None:
            self.fields["deal"] = forms.ModelChoiceField(
                label="Дело",
                queryset=ServiceDeal.objects.filter(subsystem=subsystem),
                required=False,
            )
            self.fields["job_type"] = forms.ChoiceField(
                label="Тип работ",
                required=False,
                choices=[("", "—")] + list(ServiceCustomer.JobType.choices),
            )
        _controls(self)

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if not upload:
            return upload
        name = (getattr(upload, "name", "") or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
        allowed = {"jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "pdf", "txt"}
        if ext not in allowed:
            raise forms.ValidationError("В медиатеку можно положить изображение, видео, pdf или txt.")
        return upload
