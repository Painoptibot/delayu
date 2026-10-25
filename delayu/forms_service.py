"""Формы первого этапа сервисного контура."""
import re

from django import forms
from django.contrib.auth import get_user_model

from delayu.models_service import (
    ServiceCustomer,
    ServiceDeal,
    ServiceDeployment,
    ServiceObject,
    ServiceTask,
)


def _controls(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = "form-check-input"
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = "form-select"
        else:
            widget.attrs["class"] = "form-control"
        if widget.attrs.get("type") == "date":
            widget.format = "%Y-%m-%d"
        if widget.attrs.get("type") == "datetime-local":
            widget.format = "%Y-%m-%dT%H:%M"


class CustomerForm(forms.Form):
    display_name = forms.CharField(label="Заказчик", max_length=255)
    company = forms.CharField(label="Организация", max_length=255, required=False)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)
    email = forms.EmailField(label="Почта", required=False)
    address = forms.CharField(label="Адрес", max_length=512, required=False)
    city = forms.CharField(label="Город", max_length=128, required=False)
    state = forms.CharField(label="Провинция", max_length=32, required=False)
    stage = forms.ChoiceField(label="Стадия воронки", choices=ServiceCustomer.Stage.choices)
    payment_state = forms.ChoiceField(label="Оплата", choices=ServiceCustomer.PaymentState.choices)
    invoice_amount = forms.DecimalField(
        label="Сумма счёта, C$", max_digits=12, decimal_places=2, required=False, min_value=0
    )
    tags = forms.CharField(label="Метки", max_length=255, required=False)
    notes = forms.CharField(label="Заметки", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def apply(self, customer: ServiceCustomer) -> ServiceCustomer:
        data = self.cleaned_data
        for field in (
            "display_name",
            "company",
            "phone",
            "email",
            "address",
            "city",
            "state",
            "stage",
            "payment_state",
            "tags",
            "notes",
        ):
            setattr(customer, field, data[field])
        customer.invoice_amount = data["invoice_amount"]
        customer.save()
        return customer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class ObjectForm(forms.Form):
    title = forms.CharField(label="Площадка", max_length=255)
    address = forms.CharField(label="Адрес", max_length=512, required=False)
    city = forms.CharField(label="Город", max_length=128, required=False)
    state = forms.CharField(label="Провинция", max_length=32, required=False)
    job_type = forms.ChoiceField(label="Задача", choices=ServiceCustomer.JobType.choices)
    placement = forms.ChoiceField(label="Где экран", choices=ServiceCustomer.Placement.choices)
    width_ft = forms.DecimalField(label="Ширина, ft", max_digits=6, decimal_places=1, required=False, min_value=0)
    height_ft = forms.DecimalField(label="Высота, ft", max_digits=6, decimal_places=1, required=False, min_value=0)
    event_on = forms.DateField(
        label="Дата события или монтажа",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    stage = forms.ChoiceField(label="Этап работ", choices=ServiceObject.WorkStage.choices)
    status = forms.ChoiceField(label="Статус", choices=ServiceObject.Status.choices)
    notes = forms.CharField(label="Заметки", required=False, widget=forms.Textarea(attrs={"rows": 2}))
    customer = forms.ModelChoiceField(label="Заказчик", queryset=ServiceCustomer.objects.none())

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem is not None:
            self.fields["customer"].queryset = ServiceCustomer.objects.filter(subsystem=subsystem)
        _controls(self)


class VisitForm(forms.Form):
    employee = forms.ModelChoiceField(label="Сотрудник", queryset=get_user_model().objects.none())
    departed_on = forms.DateField(
        label="Дата выезда", widget=forms.DateInput(attrs={"type": "date"})
    )
    distance_mi = forms.DecimalField(label="Мили", min_value=0, decimal_places=2, max_digits=8)
    rate_per_mile = forms.DecimalField(label="Ставка за милю, C$", min_value=0, decimal_places=2, max_digits=10)
    hours = forms.DecimalField(label="Часы на площадке", min_value=0, decimal_places=2, max_digits=8)
    hour_rate = forms.DecimalField(label="Ставка часа, C$", min_value=0, decimal_places=2, max_digits=10)
    other_cost = forms.DecimalField(
        label="Прочие издержки, C$", min_value=0, decimal_places=2, max_digits=12, required=False
    )
    note = forms.CharField(label="Комментарий", max_length=255, required=False)

    def __init__(self, *args, employees=None, **kwargs):
        super().__init__(*args, **kwargs)
        if employees is not None:
            self.fields["employee"].queryset = employees
        _controls(self)

    def clean_other_cost(self):
        return self.cleaned_data.get("other_cost") or 0


class DeploymentForm(forms.Form):
    kind = forms.ChoiceField(label="Вид", choices=ServiceDeployment.Kind.choices)
    title = forms.CharField(label="Наименование", max_length=255)
    quantity = forms.DecimalField(label="Количество", min_value=0, decimal_places=2, max_digits=10)
    unit = forms.CharField(label="Единица", max_length=32, initial="шт")
    unit_cost = forms.DecimalField(label="Цена единицы, C$", min_value=0, decimal_places=2, max_digits=12)
    note = forms.CharField(label="Комментарий", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


_DEAL_FIELDS = (
    "title",
    "stage",
    "job_type",
    "source",
    "city",
    "state",
    "venue",
    "placement",
    "width_ft",
    "height_ft",
    "timeline",
    "event_on",
    "value",
    "decision_maker",
    "screen_over_30",
    "guests_over_200",
    "church_project",
    "lost_reason",
)


class DealForm(forms.Form):
    customer = forms.ModelChoiceField(label="Заказчик", queryset=ServiceCustomer.objects.none())
    title = forms.CharField(label="Сделка", max_length=255)
    stage = forms.ChoiceField(label="Стадия", choices=ServiceCustomer.Stage.choices)
    job_type = forms.ChoiceField(label="Задача", choices=ServiceCustomer.JobType.choices)
    source = forms.CharField(label="Источник", max_length=128, required=False)
    city = forms.CharField(label="Город", max_length=128, required=False)
    state = forms.CharField(label="Провинция", max_length=32, required=False)
    venue = forms.CharField(label="Площадка события", max_length=255, required=False)
    placement = forms.ChoiceField(label="Где экран", choices=ServiceCustomer.Placement.choices)
    width_ft = forms.DecimalField(label="Ширина, ft", max_digits=6, decimal_places=1, required=False, min_value=0)
    height_ft = forms.DecimalField(label="Высота, ft", max_digits=6, decimal_places=1, required=False, min_value=0)
    timeline = forms.CharField(label="Срок проекта", max_length=255, required=False)
    event_on = forms.DateField(
        label="Дата события", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    value = forms.DecimalField(label="Сумма, C$", max_digits=12, decimal_places=2, required=False, min_value=0)
    decision_maker = forms.ChoiceField(label="Кто принимает решение", choices=ServiceDeal.Answer.choices)
    screen_over_30 = forms.ChoiceField(label="Экран больше 30 кв. футов", choices=ServiceDeal.Answer.choices)
    guests_over_200 = forms.ChoiceField(label="Гостей больше 200", choices=ServiceDeal.Answer.choices)
    church_project = forms.ChoiceField(label="Церковный проект", choices=ServiceDeal.Answer.choices)
    lost_reason = forms.CharField(label="Причина проигрыша", max_length=255, required=False)

    def __init__(self, *args, subsystem=None, lock_customer=False, **kwargs):
        super().__init__(*args, **kwargs)
        if lock_customer:
            self.fields.pop("customer")
        elif subsystem is not None:
            self.fields["customer"].queryset = ServiceCustomer.objects.filter(subsystem=subsystem)
        _controls(self)

    def apply(self, deal: ServiceDeal) -> ServiceDeal:
        data = self.cleaned_data
        previous = deal.stage
        new_stage = data["stage"]
        for field in _DEAL_FIELDS:
            if field == "stage":
                continue
            value = data[field]
            if field in {"width_ft", "height_ft", "value", "event_on"}:
                setattr(deal, field, value)
            else:
                setattr(deal, field, value if value is not None else "")
        deal.save()
        from delayu.services.service_automation import run_workflows
        from delayu.services.service_deals import mirror_customer, move_deal

        if new_stage != previous:
            move_deal(deal, new_stage)
        else:
            mirror_customer(deal)
        run_workflows(deal, "deal_ready", catalog="catalog" in (deal.source or "").lower())
        return deal


class SaleQuoteForm(forms.Form):
    display_name = forms.CharField(label="Имя", max_length=255)
    email = forms.EmailField(label="Почта", required=False)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)
    city = forms.CharField(label="Город", max_length=128, required=False)
    state = forms.CharField(label="Провинция", max_length=32, required=False)
    timeline = forms.CharField(label="Срок проекта", max_length=255, required=False)
    decision_maker = forms.ChoiceField(label="Кто принимает решение", choices=ServiceDeal.Answer.choices)
    screen_over_30 = forms.ChoiceField(label="Экран больше 30 кв. футов", choices=ServiceDeal.Answer.choices)
    church_project = forms.ChoiceField(label="Церковный проект", choices=ServiceDeal.Answer.choices)
    send_catalog = forms.BooleanField(label="Отправить каталог", required=False)
    message = forms.CharField(label="Чем помочь", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class TaskForm(forms.Form):
    title = forms.CharField(label="Задача", max_length=255)
    kind = forms.ChoiceField(
        label="Шаг",
        required=False,
        choices=ServiceTask.Kind.choices,
    )
    due_on = forms.DateField(
        label="Срок", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    note = forms.CharField(label="Заметка", max_length=255, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)


class ChannelForm(forms.Form):
    title = forms.CharField(label="Канал", max_length=64)
    detail = forms.CharField(label="Куда ложится диалог", max_length=255)
    code = forms.CharField(label="Код", max_length=32, required=False)

    def __init__(self, *args, include_code=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.include_code = include_code
        if not include_code:
            self.fields.pop("code")
        _controls(self)

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().lower()
        if not self.include_code:
            return ""
        if not code or not re.fullmatch(r"[a-z0-9_-]{2,32}", code):
            raise forms.ValidationError("Код: латиница, цифры и дефис, от 2 знаков.")
        return code


class RentalQuoteForm(forms.Form):
    display_name = forms.CharField(label="Имя", max_length=255)
    email = forms.EmailField(label="Почта", required=False)
    phone = forms.CharField(label="Телефон", max_length=32, required=False)
    location = forms.CharField(label="Город, провинция", max_length=255, required=False)
    event_on = forms.DateField(
        label="Дата события", required=False, widget=forms.DateInput(attrs={"type": "date"})
    )
    guests_over_200 = forms.ChoiceField(label="Гостей больше 200", choices=ServiceDeal.Answer.choices)
    church_project = forms.ChoiceField(label="Церковный проект", choices=ServiceDeal.Answer.choices)
    send_catalog = forms.BooleanField(label="Отправить каталог", required=False)
    message = forms.CharField(label="О событии", required=False, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _controls(self)
