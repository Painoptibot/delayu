"""Виджеты полей с автоподсказкой DaData (data-атрибуты для delayu-dadata.js)."""
from __future__ import annotations

import json

from django import forms

from delayu.forms import BOOTSTRAP


class DadataMixin:
    """Добавляет data-dadata-* к input/textarea."""

    dadata_type: str = "address"

    def __init__(
        self,
        attrs=None,
        *,
        dadata_type: str | None = None,
        dadata_parts: str | None = None,
        dadata_fill: dict[str, str] | None = None,
        dadata_geo: bool = False,
        **kwargs,
    ):
        if dadata_type is not None:
            self.dadata_type = dadata_type
        self.dadata_parts = dadata_parts
        self.dadata_fill = dadata_fill or {}
        self.dadata_geo = dadata_geo
        super().__init__(attrs, **kwargs)

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs.setdefault("class", BOOTSTRAP)
        attrs["data-dadata"] = self.dadata_type
        attrs["autocomplete"] = "off"
        if self.dadata_parts:
            attrs["data-dadata-parts"] = self.dadata_parts
        if self.dadata_fill:
            attrs["data-dadata-fill"] = json.dumps(self.dadata_fill, ensure_ascii=False)
        if self.dadata_geo:
            attrs["data-dadata-geo"] = "1"
        return attrs


class DadataTextInput(DadataMixin, forms.TextInput):
    pass


class DadataTextarea(DadataMixin, forms.Textarea):
    def __init__(self, attrs=None, *, rows=2, **kwargs):
        base = {"rows": rows, "class": BOOTSTRAP}
        if attrs:
            base.update(attrs)
        super().__init__(base, **kwargs)


class DadataSnilsInput(forms.TextInput):
    """Маска СНИЛС без API suggest (форматирование на клиенте)."""

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        attrs.setdefault("class", BOOTSTRAP)
        attrs["data-dadata-mask"] = "snils"
        attrs["placeholder"] = "000-000-000 00"
        attrs["autocomplete"] = "off"
        return attrs
