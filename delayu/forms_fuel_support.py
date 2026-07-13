"""Форма обращения в техподдержку портала жителя."""
from django import forms

from delayu.services.fuel import normalize_phone


class FuelSupportForm(forms.Form):
    name = forms.CharField(
        label="Имя",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "fuel-input", "autocomplete": "name"}),
    )
    contact = forms.CharField(
        label="Телефон или e-mail",
        max_length=255,
        widget=forms.TextInput(
            attrs={"class": "fuel-input", "placeholder": "+7 … или email", "autocomplete": "email"}
        ),
    )
    question = forms.CharField(
        label="Ваш вопрос",
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "fuel-input", "rows": 4}),
    )

    def clean_contact(self):
        raw = (self.cleaned_data.get("contact") or "").strip()
        if "@" in raw:
            return raw
        phone = normalize_phone(raw)
        if len(phone) >= 11:
            return phone
        if len(raw) < 5:
            raise forms.ValidationError("Укажите телефон или e-mail для ответа")
        return raw
