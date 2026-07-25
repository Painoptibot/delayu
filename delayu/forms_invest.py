"""Forms for invest subsystem screens."""
import json

from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin
from delayu.models import Organization
from delayu.models_invest import InvestProject, InvestSite, InvestSupportTrackItem

User = get_user_model()


def _apply_bootstrap(fields):
    for field in fields.values():
        w = field.widget
        if isinstance(w, (forms.CheckboxInput, forms.RadioSelect, forms.HiddenInput)):
            if isinstance(w, forms.HiddenInput):
                continue
            w.attrs.setdefault("class", "form-check-input")
        elif isinstance(w, forms.Select):
            w.attrs["class"] = SELECT
        elif isinstance(w, forms.Textarea):
            w.attrs.setdefault("class", BOOTSTRAP)
            w.attrs.setdefault("rows", 3)
        else:
            w.attrs.setdefault("class", BOOTSTRAP)


class InvestProjectForm(BootstrapFormMixin, forms.ModelForm):
    """Project form intentionally omits funnel; the current funnel is display-only."""

    STAGE_LABELS = {
        "lead": "Лид",
        "qualify": "Квалификация",
        "site_pick": "Подбор площадки",
        "package_ready": "Пакет готов",
        "handoff": "Передача",
        "accepted": "Принят",
        "land": "Земля",
        "permits": "Разрешения",
        "build": "Строительство",
        "commission": "Ввод",
        "archive": "Архив",
    }
    STAGE_TRANSITIONS = {
        InvestProject.Funnel.ATTRACTION: {
            "lead": ("lead", "qualify"),
            "qualify": ("qualify", "site_pick"),
            "site_pick": ("site_pick", "package_ready"),
            "package_ready": ("package_ready", "handoff"),
            "handoff": ("handoff",),
        },
        InvestProject.Funnel.SUPPORT: {
            "accepted": ("accepted", "land"),
            "land": ("land", "permits"),
            "permits": ("permits", "build"),
            "build": ("build", "commission"),
            "commission": ("commission", "archive"),
            "archive": ("archive",),
        },
    }

    class Meta:
        model = InvestProject
        fields = [
            "organization",
            "code",
            "name",
            "investor_name",
            "industry",
            "description",
            "stage",
            "owner",
            "contact_person",
            "contact_phone",
            "contact_email",
            "investment_amount",
            "jobs_count",
            "support_measures",
            "planned_start",
            "planned_end",
            "municipality_notes",
        ]
        widgets = {
            "investment_amount": forms.NumberInput(attrs={"step": "0.01"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "support_measures": forms.Textarea(attrs={"rows": 3}),
            "municipality_notes": forms.Textarea(attrs={"rows": 3}),
            "planned_start": forms.DateInput(attrs={"type": "date"}),
            "planned_end": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        subsystem = membership.subsystem if membership else getattr(self.instance, "subsystem", None)
        if subsystem:
            self.fields["organization"].queryset = subsystem.organizations.filter(is_active=True)
            self.fields["owner"].queryset = User.objects.filter(
                subsystem_memberships__subsystem=subsystem
            ).distinct()
        if self._is_mo_membership():
            self.fields["organization"].initial = membership.organization
            self.fields["organization"].widget = forms.HiddenInput()
        optional = (
            "owner",
            "investor_name",
            "industry",
            "description",
            "investment_amount",
            "jobs_count",
            "contact_person",
            "contact_phone",
            "contact_email",
            "support_measures",
            "planned_start",
            "planned_end",
            "municipality_notes",
        )
        for field_name in optional:
            self.fields[field_name].required = False
        stage_field = self.fields["stage"]
        self.fields["stage"] = forms.ChoiceField(
            label=stage_field.label,
            choices=self._stage_choices(),
            required=stage_field.required,
            widget=forms.Select,
        )
        _apply_bootstrap(self.fields)

    @property
    def display_funnel(self):
        value = self.instance.funnel or InvestProject.Funnel.ATTRACTION
        return InvestProject.Funnel(value).label

    def _stage_funnel(self):
        if self.instance and self.instance.pk:
            return self.instance.funnel or InvestProject.Funnel.ATTRACTION
        return InvestProject.Funnel.ATTRACTION

    def _current_stage(self):
        if self.instance and self.instance.pk:
            return self.instance.stage
        return "lead"

    def _allowed_stage_values(self):
        funnel_transitions = self.STAGE_TRANSITIONS.get(self._stage_funnel(), {})
        current_stage = self._current_stage()
        return funnel_transitions.get(current_stage, (current_stage,))

    def _stage_choices(self):
        return [
            (stage, self.STAGE_LABELS.get(stage, stage))
            for stage in self._allowed_stage_values()
        ]

    def _is_mo_membership(self):
        return bool(self.membership and self.membership.role.code == "invest_mo")

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if self.membership and organization.subsystem_id != self.membership.subsystem_id:
            raise forms.ValidationError("Организация должна относиться к активному инвестконтуру.")
        if self._is_mo_membership() and organization != self.membership.organization:
            raise forms.ValidationError("Организация должна совпадать с вашим МО.")
        return organization

    def clean_stage(self):
        stage = self.cleaned_data["stage"]
        if stage not in self._allowed_stage_values():
            raise forms.ValidationError("Недопустимый переход стадии для текущей воронки.")
        return stage


class InvestProjectWizardStep1Form(forms.Form):
    organization = forms.ModelChoiceField(label="МО / территория", queryset=Organization.objects.none())
    code = forms.CharField(label="Код", max_length=64)
    name = forms.CharField(label="Наименование", max_length=255)
    investor_name = forms.CharField(label="Инвестор", max_length=255, required=False)

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        if membership:
            self.fields["organization"].queryset = membership.subsystem.organizations.filter(is_active=True)
        if self._is_mo_membership():
            self.fields["organization"].initial = membership.organization
            self.fields["organization"].widget = forms.HiddenInput()
        _apply_bootstrap(self.fields)

    def _is_mo_membership(self):
        return bool(self.membership and self.membership.role.code == "invest_mo")

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if self.membership and organization.subsystem_id != self.membership.subsystem_id:
            raise forms.ValidationError("Организация должна относиться к активному инвестконтуре.")
        if self._is_mo_membership() and organization != self.membership.organization:
            raise forms.ValidationError("Организация должна совпадать с вашим МО.")
        return organization

    def clean_code(self):
        code = self.cleaned_data["code"].strip()
        if self.membership and InvestProject.objects.filter(subsystem=self.membership.subsystem, code=code).exists():
            raise forms.ValidationError("Проект с таким кодом уже есть в инвестконтуре.")
        return code


class InvestProjectWizardStep2Form(forms.Form):
    site = forms.ModelChoiceField(label="Площадка", queryset=InvestSite.objects.none(), required=False)

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        if membership:
            self.fields["site"].queryset = membership.subsystem.invest_sites.filter(
                organization__is_active=True
            ).order_by("cadastral_number")
        _apply_bootstrap(self.fields)


class InvestProjectWizardStep3Form(forms.Form):
    package_note = forms.CharField(
        label="Комментарий к пакету",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self.fields)


class InvestSupportTrackItemForm(forms.ModelForm):
    class Meta:
        model = InvestSupportTrackItem
        fields = ["title", "status", "due_at"]
        widgets = {
            "due_at": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_bootstrap(self.fields)


class InvestSiteForm(BootstrapFormMixin, forms.ModelForm):
    """Site form scoped to the active invest subsystem."""

    restriction_zones = forms.CharField(
        label="Ограничительные зоны",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="JSON-массив или по одной зоне на строку.",
    )

    class Meta:
        model = InvestSite
        fields = [
            "organization",
            "cadastral_number",
            "name",
            "address",
            "area_ha",
            "land_category",
            "vri",
            "right_type",
            "encumbrances",
            "zone_info",
            "restriction_zones",
            "status",
            "completeness_pct",
            "latitude",
            "longitude",
        ]
        widgets = {
            "area_ha": forms.NumberInput(attrs={"step": "0.0001"}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "encumbrances": forms.Textarea(attrs={"rows": 2}),
            "zone_info": forms.Textarea(attrs={"rows": 2}),
            "address": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        subsystem = membership.subsystem if membership else getattr(self.instance, "subsystem", None)
        if self.instance and self.instance.pk:
            zones = self.instance.restriction_zones or []
            if any(isinstance(zone, dict) for zone in zones):
                self.fields["restriction_zones"].initial = json.dumps(zones, ensure_ascii=False)
            else:
                self.fields["restriction_zones"].initial = "\n".join(str(zone) for zone in zones)
        if subsystem:
            self.fields["organization"].queryset = subsystem.organizations.filter(is_active=True)
        if self._is_mo_membership():
            self.fields["organization"].initial = membership.organization
            self.fields["organization"].widget = forms.HiddenInput()
        for field_name in (
            "area_ha",
            "land_category",
            "vri",
            "latitude",
            "longitude",
            "address",
            "right_type",
            "encumbrances",
            "zone_info",
            "restriction_zones",
        ):
            self.fields[field_name].required = False
        _apply_bootstrap(self.fields)

    def _is_mo_membership(self):
        return bool(self.membership and self.membership.role.code == "invest_mo")

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if self.membership and organization.subsystem_id != self.membership.subsystem_id:
            raise forms.ValidationError("Организация должна относиться к активному инвестконтуру.")
        if self._is_mo_membership() and organization != self.membership.organization:
            raise forms.ValidationError("Организация должна совпадать с вашим МО.")
        return organization

    def clean_restriction_zones(self):
        raw = (self.cleaned_data.get("restriction_zones") or "").strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise forms.ValidationError("Укажите корректный JSON-массив зон.") from exc
            if not isinstance(value, list):
                raise forms.ValidationError("Ограничительные зоны должны быть списком.")
            zones = []
            for item in value:
                if isinstance(item, dict):
                    name = str(item.get("name") or "").strip()
                    coords = item.get("coords")
                    if not name:
                        raise forms.ValidationError("Укажите name для каждой зоны.")
                    zone = {"name": name}
                    if coords:
                        if not isinstance(coords, list):
                            raise forms.ValidationError("coords зоны должны быть списком координат.")
                        zone["coords"] = coords
                    zones.append(zone)
                else:
                    label = str(item).strip()
                    if label:
                        zones.append(label)
            return zones
        return [line.strip() for line in raw.replace(",", "\n").splitlines() if line.strip()]
