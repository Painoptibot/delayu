"""M74 — применение FormSchema к делам и реестрам."""
from django import forms

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models import FormSchema, RegistryType


def normalize_schema(raw) -> list:
    if not raw:
        return []
    if isinstance(raw, str):
        from delayu.services.registries import parse_field_schema

        return parse_field_schema(raw)
    if not isinstance(raw, list):
        return []
    out = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        spec = {
            "key": str(item["key"]).strip(),
            "label": str(item.get("label") or item["key"]).strip(),
            "required": bool(item.get("required")),
        }
        ftype = (item.get("type") or "text").strip()
        spec["type"] = ftype
        if ftype == "select" and item.get("nsi_classifier"):
            spec["nsi_classifier"] = str(item["nsi_classifier"]).strip()
        out.append(spec)
    return out


def get_form_schema(subsystem, target, code=None):
    qs = FormSchema.objects.filter(subsystem=subsystem, target=target, is_active=True)
    if code:
        return qs.filter(code=code).first()
    return qs.order_by("code").first()


def resolve_registry_schema(registry_type: RegistryType) -> list:
    fs = get_form_schema(
        registry_type.subsystem, FormSchema.Target.REGISTRY, registry_type.code
    )
    if fs and fs.schema:
        return normalize_schema(fs.schema)
    return normalize_schema(registry_type.field_schema)


def sync_registry_form_schema(form_schema: FormSchema):
    if form_schema.target != FormSchema.Target.REGISTRY or not form_schema.schema:
        return
    RegistryType.objects.filter(
        subsystem=form_schema.subsystem, code=form_schema.code
    ).update(field_schema=form_schema.schema)


def validate_schema_data(schema: list, data: dict) -> tuple[dict, dict]:
    cleaned = {}
    errors = {}
    for field in schema:
        key = field["key"]
        val = data.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        if field.get("required") and not val:
            errors[key] = "Обязательное поле"
        cleaned[key] = val
    return cleaned, errors


def build_dynamic_form(schema: list, *, initial=None, data=None, prefix="", subsystem=None):
    fields = {}
    for spec in schema:
        key = spec["key"]
        field_name = f"{prefix}{key}" if prefix else key
        label = spec.get("label", key)
        required = bool(spec.get("required"))
        ftype = spec.get("type", "text")
        if ftype == "select" and spec.get("nsi_classifier") and subsystem:
            from delayu.services.nsi_choices import choices_for

            choices = choices_for(subsystem, spec["nsi_classifier"], fallback=[])
            field = forms.ChoiceField(
                label=label,
                required=required,
                choices=[("", "—")] + list(choices),
                widget=forms.Select(attrs={"class": BOOTSTRAP}),
            )
        elif ftype == "textarea":
            widget = forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3})
            field = forms.CharField(label=label, required=required, widget=widget)
        else:
            field = forms.CharField(
                label=label,
                required=required,
                widget=forms.TextInput(attrs={"class": BOOTSTRAP}),
            )
        fields[field_name] = field
    form_class = type("DynamicSchemaForm", (BootstrapFormMixin, forms.Form), fields)
    if data is not None:
        return form_class(data)
    init = {}
    if initial:
        for spec in schema:
            k = spec["key"]
            fn = f"{prefix}{k}" if prefix else k
            init[fn] = initial.get(k, "")
    return form_class(initial=init)


def extract_schema_values(form, schema: list, *, prefix="") -> dict:
    out = {}
    for spec in schema:
        key = spec["key"]
        fn = f"{prefix}{key}" if prefix else key
        if fn in form.cleaned_data:
            out[key] = form.cleaned_data[fn]
    return out


def case_schema(subsystem):
    fs = get_form_schema(subsystem, FormSchema.Target.CASE)
    if not fs:
        return []
    return normalize_schema(fs.schema)


def case_extra_context(case, *, prefix="extra_"):
    schema = case_schema(case.subsystem)
    if not schema:
        return {"form_schema": None, "extra_form": None, "extra_display": []}
    fs = get_form_schema(case.subsystem, FormSchema.Target.CASE)
    return {
        "form_schema": fs,
        "extra_form": build_dynamic_form(
            schema, initial=case.extra_data or {}, prefix=prefix, subsystem=case.subsystem
        ),
        "extra_display": [
            (f.get("label", f["key"]), (case.extra_data or {}).get(f["key"], ""))
            for f in schema
            if (case.extra_data or {}).get(f["key"], "")
        ],
    }


def save_case_extra_data(case, extra_form, schema: list, *, prefix="extra_"):
    merged = dict(case.extra_data or {})
    merged.update(extract_schema_values(extra_form, schema, prefix=prefix))
    case.extra_data = merged
    case.save(update_fields=["extra_data", "updated_at"])
