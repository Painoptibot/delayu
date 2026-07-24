"""Forms for invest subsystem screens."""

from django import forms
from django.contrib.auth import get_user_model

from delayu.models import SubsystemMembership
from delayu.models_invest import InvestProject, InvestSite

User = get_user_model()


class InvestProjectForm(forms.ModelForm):
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
            "stage",
            "owner",
            "investment_amount",
            "jobs_count",
        ]
        widgets = {
            "investment_amount": forms.NumberInput(attrs={"step": "0.01"}),
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
        self.fields["owner"].required = False
        self.fields["investor_name"].required = False
        self.fields["industry"].required = False
        self.fields["investment_amount"].required = False
        self.fields["jobs_count"].required = False
        stage_field = self.fields["stage"]
        self.fields["stage"] = forms.ChoiceField(
            label=stage_field.label,
            choices=self._stage_choices(),
            required=stage_field.required,
            widget=forms.Select,
        )

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


class InvestSiteForm(forms.ModelForm):
    """Site form scoped to the active invest subsystem."""

    class Meta:
        model = InvestSite
        fields = [
            "organization",
            "cadastral_number",
            "name",
            "area_ha",
            "land_category",
            "vri",
            "status",
            "completeness_pct",
            "latitude",
            "longitude",
        ]
        widgets = {
            "area_ha": forms.NumberInput(attrs={"step": "0.0001"}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001"}),
        }

    def __init__(self, *args, membership=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.membership = membership
        subsystem = membership.subsystem if membership else getattr(self.instance, "subsystem", None)
        if subsystem:
            self.fields["organization"].queryset = subsystem.organizations.filter(is_active=True)
        if self._is_mo_membership():
            self.fields["organization"].initial = membership.organization
            self.fields["organization"].widget = forms.HiddenInput()
        for field_name in ("area_ha", "land_category", "vri", "latitude", "longitude"):
            self.fields[field_name].required = False

    def _is_mo_membership(self):
        return bool(self.membership and self.membership.role.code == "invest_mo")

    def clean_organization(self):
        organization = self.cleaned_data["organization"]
        if self.membership and organization.subsystem_id != self.membership.subsystem_id:
            raise forms.ValidationError("Организация должна относиться к активному инвестконтуру.")
        if self._is_mo_membership() and organization != self.membership.organization:
            raise forms.ValidationError("Организация должна совпадать с вашим МО.")
        return organization
