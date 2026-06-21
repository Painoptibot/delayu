from datetime import timedelta

from django import forms
from django.contrib.auth import get_user_model

from delayu.forms import BOOTSTRAP, SELECT, BootstrapFormMixin, DatePickerInput
from delayu.widgets_dadata import DadataSnilsInput, DadataTextarea, DadataTextInput
from delayu.services.uzhv_nsi import nsi_value_choices
from delayu.models_uzhv import (
    HousingAppeal,
    HousingAppealAttachment,
    HousingCaseAttachment,
    HousingCitizen,
    HousingContract,
    HousingContractAttachment,
    HousingContractConsent,
    HousingCourtCase,
    HousingEnforcementProceeding,
    HousingAdminProtocol,
    HousingHouseholdMember,
    HousingInspection,
    HousingInspectionOrder,
    HousingInspectionPlan,
    HousingInteragencyRequest,
    HousingPrescription,
    HousingQueueCase,
    MunicipalBuilding,
    MunicipalPremise,
    PrivateManagedPremise,
    HousingPersonalAccount,
    HousingPersonalAccountMember,
)

User = get_user_model()


def _assignee_qs(subsystem):
    return User.objects.filter(subsystem_memberships__subsystem=subsystem).distinct().order_by(
        "last_name", "username"
    )


class HousingCitizenForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingCitizen
        fields = [
            "last_name",
            "first_name",
            "middle_name",
            "snils",
            "passport_series",
            "passport_number",
            "passport_issued_at",
            "passport_issued_by",
            "birth_date",
            "phone",
            "email",
            "reg_address",
        ]
        widgets = {
            "last_name": DadataTextInput(
                dadata_type="fio",
                dadata_parts="SURNAME",
                dadata_fill={"first_name": "name", "middle_name": "patronymic"},
            ),
            "first_name": DadataTextInput(dadata_type="fio", dadata_parts="NAME"),
            "middle_name": DadataTextInput(dadata_type="fio", dadata_parts="PATRONYMIC"),
            "snils": DadataSnilsInput(),
            "phone": DadataTextInput(dadata_type="phone"),
            "email": DadataTextInput(dadata_type="email"),
            "passport_series": DadataTextInput(
                dadata_type="passport",
                dadata_fill={"passport_number": "number"},
            ),
            "passport_number": DadataTextInput(dadata_type="passport"),
            "passport_issued_by": DadataTextarea(dadata_type="fms_unit", rows=2),
            "reg_address": DadataTextarea(dadata_type="address", rows=2),
            "birth_date": DatePickerInput(),
            "passport_issued_at": DatePickerInput(),
        }


class HousingQueueCaseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingQueueCase
        fields = [
            "citizen",
            "case_number",
            "category",
            "status",
            "registered_at",
            "assignee",
            "income_verified",
            "low_income_conclusion",
            "household_size",
            "monthly_income",
            "property_value",
            "removed_at",
            "removal_reason",
            "notes",
        ]
        widgets = {
            "registered_at": DatePickerInput(),
            "removed_at": DatePickerInput(),
            "low_income_conclusion": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "category": forms.Select(attrs={"class": SELECT}),
            "status": forms.Select(attrs={"class": SELECT}),
            "removal_reason": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            self.fields["assignee"].queryset = _assignee_qs(subsystem)
            self.fields["assignee"].required = False
            self.fields["assignee"].help_text = (
                "Ответственный специалист по делу / заявлению о малоимущих"
            )


class HousingAppealRegisterForm(BootstrapFormMixin, forms.ModelForm):
    """Регистрация нового обращения (без ответа)."""

    class Meta:
        model = HousingAppeal
        fields = ["citizen", "housing_case", "subject", "body", "received_at", "assignee"]
        widgets = {
            "received_at": DatePickerInput(),
            "body": forms.Textarea(attrs={"rows": 4, "class": BOOTSTRAP}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            self.fields["housing_case"].queryset = HousingQueueCase.objects.filter(
                subsystem=subsystem
            ).select_related("citizen")
            self.fields["assignee"].queryset = _assignee_qs(subsystem)
            for f in ("citizen", "housing_case", "assignee"):
                self.fields[f].required = False


class HousingAppealForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingAppeal
        fields = [
            "citizen",
            "housing_case",
            "subject",
            "body",
            "received_at",
            "assignee",
            "status",
            "conclusion_kind",
            "answer_text",
            "answered_at",
        ]
        widgets = {
            "received_at": DatePickerInput(),
            "answered_at": DatePickerInput(),
            "body": forms.Textarea(attrs={"rows": 4, "class": BOOTSTRAP}),
            "answer_text": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
            "conclusion_kind": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            self.fields["housing_case"].queryset = HousingQueueCase.objects.filter(
                subsystem=subsystem
            ).select_related("citizen")
            self.fields["assignee"].queryset = _assignee_qs(subsystem)
            for f in ("citizen", "housing_case", "assignee", "answered_at", "conclusion_kind"):
                self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        if status in (HousingAppeal.Status.ANSWERED, HousingAppeal.Status.CLOSED):
            if not cleaned.get("answer_text", "").strip():
                self.add_error("answer_text", "Укажите текст ответа")
        return cleaned


class MunicipalBuildingForm(BootstrapFormMixin, forms.ModelForm):
    geocode_from_address = forms.BooleanField(
        label="Определить координаты по адресу при сохранении",
        required=False,
        initial=False,
        help_text="Если широта и долгота не указаны — DaData (при DADATA_API_KEY) или HTTP Геокодер Яндекса (YANDEX_MAPS_API_KEY).",
    )

    class Meta:
        model = MunicipalBuilding
        fields = [
            "address",
            "cadastral_number",
            "floors",
            "year_built",
            "condition",
            "total_area_sqm",
            "residents_count",
            "in_resettlement_program",
            "in_reconstruction_zone",
            "reconstruction_program",
            "reconstruction_since",
            "latitude",
            "longitude",
            "notes",
        ]
        widgets = {
            "address": DadataTextInput(dadata_type="address", dadata_geo=True),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "condition": forms.Select(attrs={"class": SELECT}),
            "reconstruction_program": forms.TextInput(attrs={"class": BOOTSTRAP}),
            "reconstruction_since": DatePickerInput(),
        }

    def clean(self):
        cleaned = super().clean()
        lat = cleaned.get("latitude")
        lng = cleaned.get("longitude")
        address = (cleaned.get("address") or "").strip()
        if cleaned.get("geocode_from_address") and address and (lat is None or lng is None):
            from delayu.services.uzhv_map import geocode_address

            lat, lng = geocode_address(address)
            cleaned["latitude"] = lat
            cleaned["longitude"] = lng
        if (lat is None) ^ (lng is None):
            raise forms.ValidationError("Укажите и широту, и долготу, либо оставьте оба поля пустыми.")
        return cleaned


class MunicipalPremiseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = MunicipalPremise
        fields = [
            "number",
            "area_sqm",
            "rooms",
            "status",
            "unfit_for_living",
            "unfit_decision_ref",
            "unfit_decision_at",
            "unfit_reason",
            "usable_for_purpose",
            "specialized_orphan",
        ]
        widgets = {
            "status": forms.Select(attrs={"class": SELECT}),
            "unfit_decision_at": DatePickerInput(),
            "unfit_reason": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }



class HousingCaseAttachmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingCaseAttachment
        fields = ["title", "doc_kind", "file"]
        widgets = {
            "doc_kind": forms.Select(attrs={"class": SELECT}),
        }


class HousingAppealAttachmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingAppealAttachment
        fields = ["title", "doc_kind", "file"]
        widgets = {
            "doc_kind": forms.Select(attrs={"class": SELECT}),
        }


class HousingInspectionPlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingInspectionPlan
        fields = [
            "plan_number",
            "title",
            "period_from",
            "period_to",
            "basis",
            "status",
            "approved_at",
            "notes",
        ]
        widgets = {
            "period_from": DatePickerInput(),
            "period_to": DatePickerInput(),
            "approved_at": DatePickerInput(),
            "basis": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["approved_at"].required = False


class HousingInspectionOrderForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingInspectionOrder
        fields = [
            "order_number",
            "addressee",
            "object_type",
            "building",
            "check_address",
            "check_subject",
            "plan",
            "issued_at",
            "conduct_by",
            "status",
            "notes",
        ]
        widgets = {
            "issued_at": DatePickerInput(),
            "conduct_by": DatePickerInput(),
            "object_type": forms.Select(attrs={"class": SELECT}),
            "addressee": DadataTextInput(dadata_type="party"),
            "check_address": DadataTextarea(dadata_type="address", rows=2),
            "status": forms.Select(attrs={"class": SELECT}),
            "plan": forms.Select(attrs={"class": SELECT}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["building"].queryset = MunicipalBuilding.objects.filter(subsystem=subsystem)
            self.fields["plan"].queryset = HousingInspectionPlan.objects.filter(
                subsystem=subsystem
            ).exclude(status=HousingInspectionPlan.Status.COMPLETED)
            self.fields["building"].required = False
            self.fields["plan"].required = False


class HousingInspectionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingInspection
        fields = [
            "plan",
            "inspection_number",
            "inspection_type",
            "object_type",
            "building",
            "counterparty_name",
            "check_subject",
            "planned_date",
            "completed_date",
            "inspector",
            "status",
            "result_summary",
            "violations_found",
        ]
        widgets = {
            "planned_date": DatePickerInput(),
            "completed_date": DatePickerInput(),
            "counterparty_name": DadataTextInput(dadata_type="party"),
            "result_summary": forms.Textarea(attrs={"rows": 4, "class": BOOTSTRAP}),
            "inspection_type": forms.Select(attrs={"class": SELECT}),
            "object_type": forms.Select(attrs={"class": SELECT}),
            "status": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["building"].queryset = MunicipalBuilding.objects.filter(
                subsystem=subsystem
            )
            self.fields["plan"].queryset = HousingInspectionPlan.objects.filter(
                subsystem=subsystem
            ).exclude(status=HousingInspectionPlan.Status.COMPLETED).order_by("-period_from")
            self.fields["plan"].required = False
            self.fields["inspector"].queryset = _assignee_qs(subsystem)
            self.fields["building"].required = False
            self.fields["inspector"].required = False
            self.fields["completed_date"].required = False
            subjects = nsi_value_choices(subsystem, "uzhv_inspection_subjects")
            if subjects:
                self.fields["check_subject"] = forms.ChoiceField(
                    choices=[("", "— выберите —")] + subjects,
                    required=False,
                    widget=forms.Select(attrs={"class": SELECT}),
                    label="Предмет проверки",
                )


class HousingPrescriptionForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingPrescription
        fields = [
            "prescription_number",
            "issued_at",
            "due_date",
            "description",
            "status",
            "fulfilled_at",
        ]
        widgets = {
            "issued_at": DatePickerInput(),
            "due_date": DatePickerInput(),
            "fulfilled_at": DatePickerInput(),
            "description": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
        }


class HousingCourtCaseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingCourtCase
        fields = [
            "inspection",
            "prescription",
            "court_name",
            "case_number",
            "check_address",
            "defendant_name",
            "next_hearing_date",
            "ufssp_reference",
            "status",
            "notes",
        ]
        widgets = {
            "court_name": DadataTextInput(dadata_type="party"),
            "defendant_name": DadataTextInput(dadata_type="fio"),
            "check_address": DadataTextarea(dadata_type="address", rows=2),
            "next_hearing_date": DatePickerInput(),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["inspection"].queryset = HousingInspection.objects.filter(
                subsystem=subsystem
            ).order_by("-planned_date")
            self.fields["prescription"].queryset = HousingPrescription.objects.filter(
                inspection__subsystem=subsystem
            ).select_related("inspection")
            for f in ("inspection", "prescription", "next_hearing_date", "ufssp_reference"):
                self.fields[f].required = False


class HousingEnforcementProceedingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingEnforcementProceeding
        fields = [
            "court_case",
            "proceeding_number",
            "debtor_name",
            "check_address",
            "court_decision",
            "initiated_at",
            "completed_at",
            "bailiff_office",
            "status",
            "notes",
        ]
        widgets = {
            "initiated_at": DatePickerInput(),
            "completed_at": DatePickerInput(),
            "check_address": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "court_decision": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["court_case"].queryset = HousingCourtCase.objects.filter(
                subsystem=subsystem
            ).order_by("-next_hearing_date")
            self.fields["completed_at"].required = False


class HousingInteragencyRequestForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingInteragencyRequest
        fields = [
            "request_number",
            "request_type",
            "channel",
            "recipient_name",
            "subject",
            "housing_case",
            "citizen",
            "sent_at",
            "due_date",
            "answered_at",
            "response_summary",
            "status",
        ]
        widgets = {
            "recipient_name": DadataTextInput(dadata_type="party"),
            "sent_at": DatePickerInput(),
            "due_date": DatePickerInput(),
            "answered_at": DatePickerInput(),
            "subject": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "response_summary": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "request_type": forms.Select(attrs={"class": SELECT}),
            "channel": forms.Select(attrs={"class": SELECT}),
            "status": forms.Select(attrs={"class": SELECT}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["housing_case"].queryset = HousingQueueCase.objects.filter(
                subsystem=subsystem
            ).select_related("citizen")
            self.fields["citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            for f in ("housing_case", "citizen", "answered_at"):
                self.fields[f].required = False


class HousingAdminProtocolForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingAdminProtocol
        fields = [
            "protocol_number",
            "protocol_date",
            "legal_article",
            "violator_name",
            "fine_amount",
            "status",
            "notes",
        ]
        widgets = {
            "violator_name": DadataTextInput(dadata_type="fio"),
            "protocol_date": DatePickerInput(),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "status": forms.Select(attrs={"class": SELECT}),
        }


class HousingContractForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingContract
        fields = [
            "contract_number",
            "contract_type",
            "citizen",
            "premise",
            "signed_at",
            "valid_until",
            "is_active",
            "terminated_at",
            "termination_reason",
            "notes",
        ]
        widgets = {
            "signed_at": DatePickerInput(),
            "valid_until": DatePickerInput(),
            "terminated_at": DatePickerInput(),
            "contract_type": forms.Select(attrs={"class": SELECT}),
            "termination_reason": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            self.fields["premise"].queryset = MunicipalPremise.objects.filter(
                building__subsystem=subsystem
            ).select_related("building")
            self.fields["premise"].required = False
            self.fields["valid_until"].required = False
            self.fields["terminated_at"].required = False
            self.fields["termination_reason"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_active") is False and not cleaned.get("termination_reason", "").strip():
            self.add_error("termination_reason", "Укажите основание расторжения")
        return cleaned


class HousingContractConsentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingContractConsent
        fields = [
            "consent_type",
            "decision",
            "subject",
            "document_number",
            "registered_at",
            "notes",
        ]
        widgets = {
            "consent_type": forms.Select(attrs={"class": SELECT}),
            "decision": forms.Select(attrs={"class": SELECT}),
            "registered_at": DatePickerInput(),
            "subject": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }


class HousingContractAttachmentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingContractAttachment
        fields = ["title", "doc_kind", "file"]
        widgets = {
            "doc_kind": forms.Select(attrs={"class": SELECT}),
        }


class HousingPersonalAccountForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingPersonalAccount
        fields = [
            "account_number",
            "tenant_citizen",
            "living_area_sqm",
            "total_area_sqm",
            "utility_services",
            "is_active",
            "opened_at",
            "closed_at",
            "notes",
        ]
        widgets = {
            "opened_at": DatePickerInput(),
            "closed_at": DatePickerInput(),
            "utility_services": forms.Textarea(attrs={"rows": 3, "class": BOOTSTRAP}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }

    def __init__(self, *args, subsystem=None, **kwargs):
        super().__init__(*args, **kwargs)
        if subsystem:
            self.fields["tenant_citizen"].queryset = HousingCitizen.objects.filter(
                subsystem=subsystem
            ).order_by("last_name", "first_name")
            self.fields["tenant_citizen"].required = False
            self.fields["closed_at"].required = False


class HousingPersonalAccountMemberForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingPersonalAccountMember
        fields = [
            "full_name",
            "relation",
            "birth_date",
            "registered_from",
            "registered_to",
            "sort_order",
        ]
        widgets = {
            "relation": forms.Select(attrs={"class": SELECT}),
            "birth_date": DatePickerInput(),
            "registered_from": DatePickerInput(),
            "registered_to": DatePickerInput(),
        }


class PrivateManagedPremiseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = PrivateManagedPremise
        fields = [
            "address",
            "premise_number",
            "cadastral_number",
            "area_sqm",
            "rooms",
            "owner_name",
            "owner_phone",
            "management_since",
            "notes",
        ]
        widgets = {
            "address": DadataTextarea(dadata_type="address", rows=2),
            "owner_name": DadataTextInput(dadata_type="fio"),
            "owner_phone": DadataTextInput(dadata_type="phone"),
            "management_since": DatePickerInput(),
            "notes": forms.Textarea(attrs={"rows": 2, "class": BOOTSTRAP}),
        }


class HousingHouseholdMemberForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = HousingHouseholdMember
        fields = [
            "full_name",
            "relation",
            "birth_date",
            "snils",
            "passport_series",
            "passport_number",
            "reg_address",
            "monthly_income",
            "sort_order",
        ]
        widgets = {
            "full_name": DadataTextInput(dadata_type="fio"),
            "snils": DadataSnilsInput(),
            "passport_series": DadataTextInput(
                dadata_type="passport",
                dadata_fill={"passport_number": "number"},
            ),
            "passport_number": DadataTextInput(dadata_type="passport"),
            "reg_address": DadataTextarea(dadata_type="address", rows=2),
            "birth_date": DatePickerInput(),
            "relation": forms.Select(attrs={"class": SELECT}),
        }


HousingHouseholdMemberFormSet = forms.inlineformset_factory(
    HousingQueueCase,
    HousingHouseholdMember,
    form=HousingHouseholdMemberForm,
    extra=1,
    can_delete=True,
)
