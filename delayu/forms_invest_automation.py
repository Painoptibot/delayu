from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models_invest import InvestAutomationConfig
from delayu.services.invest_flags import DEFAULT_FIELD_MAPPING_V1, DEFAULT_STAGE_MAPPING_V1


FLAG_LABELS = {
    "bitrix_inbound": "Bitrix inbound (webhook)",
    "bitrix_outbound": "Bitrix outbound push",
    "bitrix_full_duplex": "Full duplex",
    "smev_mock": "СМЭВ mock",
    "smev_live": "СМЭВ live",
    "auto_package": "Авто-пакет",
    "auto_smev": "Авто СМЭВ",
    "auto_site_match": "Авто-подбор площадок",
    "auto_mo_tasks": "Авто-задачи МО",
    "auto_tp_tasks": "Авто-задачи ТП",
    "auto_escalations": "Эскалации SLA",
    "gate_before_outbound": "Gate перед outbound",
    "sandbox": "Sandbox",
}


class InvestAutomationConnectionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = InvestAutomationConfig
        fields = ("bitrix_api_base", "bitrix_webhook_token", "allowed_ips", "contract_version")
        widgets = {
            "allowed_ips": forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3}),
        }

    def clean_bitrix_webhook_token(self):
        token = (self.cleaned_data.get("bitrix_webhook_token") or "").strip()
        flags = self.instance.get_flags() if self.instance and self.instance.pk else dict(
            InvestAutomationConfig.DEFAULT_FLAGS
        )
        if flags.get("bitrix_inbound") and not token:
            raise ValidationError("Токен обязателен при включённом bitrix_inbound.")
        return token

    def clean_allowed_ips(self):
        value = self.cleaned_data.get("allowed_ips") or []
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValidationError("Укажите JSON-массив строк, например [\"10.0.0.1\"].")
        return [item.strip() for item in value if item.strip()]


class InvestAutomationFlagsForm(forms.Form):
    def __init__(self, *args, initial_flags=None, **kwargs):
        super().__init__(*args, **kwargs)
        flags = dict(InvestAutomationConfig.DEFAULT_FLAGS)
        flags.update(initial_flags or {})
        for key, label in FLAG_LABELS.items():
            self.fields[key] = forms.BooleanField(
                required=False,
                label=label,
                initial=bool(flags.get(key, False)),
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
            )

    def cleaned_flags(self) -> dict:
        out = dict(InvestAutomationConfig.DEFAULT_FLAGS)
        for key in FLAG_LABELS:
            out[key] = bool(self.cleaned_data.get(key))
        return out


class InvestAutomationMappingForm(forms.Form):
    field_rows = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 10}),
        help_text="По одной строке: BITRIX_FIELD=delayu_attr",
    )
    stage_rows = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 8}),
        help_text="По одной строке: STAGE_ID=funnel/stage",
    )

    @staticmethod
    def serialize_field_mapping(mapping: dict) -> str:
        return "\n".join(f"{k}={v}" for k, v in (mapping or {}).items())

    @staticmethod
    def serialize_stage_mapping(mapping: dict) -> str:
        lines = []
        for k, v in (mapping or {}).items():
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                lines.append(f"{k}={v[0]}/{v[1]}")
            else:
                lines.append(f"{k}={v}")
        return "\n".join(lines)

    def cleaned_field_mapping(self) -> dict:
        result = {}
        for line in (self.cleaned_data.get("field_rows") or "").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if key and val:
                result[key] = val
        return result

    def clean_stage_rows(self):
        rows = self.cleaned_data.get("stage_rows") or ""
        errors = []
        for line_no, line in enumerate(rows.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            if "=" not in line:
                errors.append(f"Строка {line_no}: укажите STAGE_ID=funnel/stage.")
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if not key:
                errors.append(f"Строка {line_no}: укажите идентификатор стадии Bitrix.")
                continue
            if "/" not in val:
                errors.append(f"Строка {line_no}: укажите значение в формате funnel/stage.")
                continue
            funnel, stage = val.split("/", 1)
            if not funnel.strip() or not stage.strip():
                errors.append(f"Строка {line_no}: funnel и stage не должны быть пустыми.")
        if errors:
            raise ValidationError(errors)
        return rows

    def cleaned_stage_mapping(self) -> dict:
        result = {}
        for line in (self.cleaned_data.get("stage_rows") or "").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if not key or not val:
                continue
            if "/" not in val:
                continue
            funnel, stage = val.split("/", 1)
            funnel, stage = funnel.strip(), stage.strip()
            if funnel and stage:
                result[key] = [funnel, stage]
        return result

    @classmethod
    def from_config(cls, cfg: InvestAutomationConfig):
        return cls(
            initial={
                "field_rows": cls.serialize_field_mapping(
                    cfg.field_mapping or DEFAULT_FIELD_MAPPING_V1
                ),
                "stage_rows": cls.serialize_stage_mapping(
                    cfg.stage_mapping or DEFAULT_STAGE_MAPPING_V1
                ),
            }
        )
