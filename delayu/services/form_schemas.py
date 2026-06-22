"""M74 — применение FormSchema к делам и реестрам."""
import re

from django import forms

from delayu.forms import BOOTSTRAP, BootstrapFormMixin
from delayu.models import FormSchema, RegistryType


def field_visible(spec: dict, data: dict) -> bool:
    """Условная видимость поля по данным формы."""
    cond = spec.get("visible_when")
    if not cond or not isinstance(cond, dict):
        return True
    fk = cond.get("field")
    if not fk:
        return True
    val = data.get(fk, "")
    if cond.get("filled"):
        return bool(str(val).strip())
    if "equals" in cond:
        return str(val) == str(cond.get("equals"))
    return True


def filter_visible_schema(schema: list, data: dict) -> list:
    return [f for f in schema if f.get("type") != "section" and field_visible(f, data or {})]


def schema_sections(schema: list) -> list[dict]:
    """Группы полей по секциям для карточки дела."""
    sections: list[dict] = []
    current = {"id": "", "title": "Основное", "fields": []}
    for spec in schema or []:
        if spec.get("type") == "section":
            if current["fields"]:
                sections.append(current)
            current = {
                "id": spec.get("key") or spec.get("label", "section"),
                "title": spec.get("label") or "Секция",
                "fields": [],
            }
            continue
        sec_name = spec.get("section")
        if sec_name and (not current["id"] or current["title"] == "Основное"):
            if current["fields"]:
                sections.append(current)
            current = {"id": sec_name, "title": sec_name, "fields": []}
        current["fields"].append(spec)
    if current["fields"]:
        sections.append(current)
    return sections or [{"id": "main", "title": "Основное", "fields": list(schema or [])}]


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
        if ftype == "section":
            spec["required"] = False
        if item.get("section"):
            spec["section"] = str(item["section"]).strip()
        if ftype == "select" and item.get("nsi_classifier"):
            spec["nsi_classifier"] = str(item["nsi_classifier"]).strip()
        if ftype == "lookup":
            if item.get("registry_code"):
                spec["registry_code"] = str(item["registry_code"]).strip()
            if item.get("lookup_label_field"):
                spec["lookup_label_field"] = str(item["lookup_label_field"]).strip()
            fill = item.get("fill_map")
            if isinstance(fill, dict):
                spec["fill_map"] = {str(k): str(v) for k, v in fill.items()}
        vw = item.get("visible_when")
        if isinstance(vw, dict) and vw.get("field"):
            spec["visible_when"] = {
                "field": str(vw["field"]).strip(),
                **({"equals": str(vw["equals"])} if "equals" in vw else {}),
                **({"filled": True} if vw.get("filled") else {}),
            }
        if item.get("pattern"):
            spec["pattern"] = str(item["pattern"]).strip()
        if item.get("min") is not None and item.get("min") != "":
            spec["min"] = item["min"]
        if item.get("max") is not None and item.get("max") != "":
            spec["max"] = item["max"]
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
    visible = filter_visible_schema(schema, data)
    visible_keys = {f["key"] for f in visible}
    for field in schema:
        if field.get("type") == "section":
            continue
        key = field["key"]
        if key not in visible_keys:
            continue
        val = data.get(key, "")
        if isinstance(val, str):
            val = val.strip()
        required = field.get("required") and field_visible(field, data)
        if required and not val:
            errors[key] = "Обязательное поле"
        if val and field.get("pattern"):
            try:
                if not re.match(field["pattern"], str(val)):
                    errors[key] = "Неверный формат"
            except re.error:
                pass
        if val and field.get("type") == "number":
            try:
                num = float(str(val).replace(",", "."))
                if field.get("min") is not None and num < float(field["min"]):
                    errors[key] = f"Минимум {field['min']}"
                if field.get("max") is not None and num > float(field["max"]):
                    errors[key] = f"Максимум {field['max']}"
            except ValueError:
                errors[key] = "Введите число"
        cleaned[key] = val
    return cleaned, errors


def build_dynamic_form(schema: list, *, initial=None, data=None, prefix="", subsystem=None):
    fields = {}
    for spec in schema:
        if spec.get("type") == "section":
            continue
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
        elif ftype == "lookup" and spec.get("registry_code") and subsystem:
            from delayu.models import RegistryRecord, RegistryType

            rt = RegistryType.objects.filter(
                subsystem=subsystem, code=spec["registry_code"], is_active=True
            ).first()
            choices = [("", "—")]
            if rt:
                label_field = spec.get("lookup_label_field") or "name"
                for rec in RegistryRecord.objects.filter(registry_type=rt).order_by("-pk")[:200]:
                    rec_data = rec.data or {}
                    rec_label = rec_data.get(label_field) or rec.external_id or str(rec.pk)
                    choices.append((str(rec.pk), str(rec_label)[:120]))
            import json as _json

            field = forms.ChoiceField(
                label=label,
                required=required,
                choices=choices,
                widget=forms.Select(
                    attrs={
                        "class": BOOTSTRAP,
                        "data-lookup-registry": spec.get("registry_code", ""),
                        "data-fill-map": _json.dumps(spec.get("fill_map") or {}),
                    }
                ),
            )
        elif ftype == "textarea":
            widget = forms.Textarea(attrs={"class": BOOTSTRAP, "rows": 3})
            field = forms.CharField(label=label, required=required, widget=widget)
        elif ftype == "number":
            field = forms.FloatField(
                label=label,
                required=required,
                widget=forms.NumberInput(attrs={"class": BOOTSTRAP}),
            )
        else:
            widget_attrs = {"class": BOOTSTRAP}
            if spec.get("pattern"):
                widget_attrs["pattern"] = spec["pattern"]
            field = forms.CharField(
                label=label,
                required=required,
                widget=forms.TextInput(attrs=widget_attrs),
            )
        vw = spec.get("visible_when")
        if vw:
            field.widget.attrs["data-visible-field"] = vw.get("field", "")
            if "equals" in vw:
                field.widget.attrs["data-visible-equals"] = vw.get("equals", "")
            if vw.get("filled"):
                field.widget.attrs["data-visible-filled"] = "1"
        fields[field_name] = field
    form_class = type("DynamicSchemaForm", (BootstrapFormMixin, forms.Form), fields)
    if data is not None:
        return form_class(data)
    init = {}
    if initial:
        for spec in schema:
            if spec.get("type") == "section":
                continue
            k = spec["key"]
            fn = f"{prefix}{k}" if prefix else k
            init[fn] = initial.get(k, "")
    return form_class(initial=init)


def extract_schema_values(form, schema: list, *, prefix="") -> dict:
    out = {}
    for spec in schema:
        if spec.get("type") == "section":
            continue
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
        return {
            "form_schema": None,
            "extra_form": None,
            "extra_display": [],
            "form_sections": [],
            "extra_fields_by_section": [],
        }
    fs = get_form_schema(case.subsystem, FormSchema.Target.CASE)
    extra_form = build_dynamic_form(
        schema, initial=case.extra_data or {}, prefix=prefix, subsystem=case.subsystem
    )
    sections = schema_sections(schema)
    by_section = []
    for sec in sections:
        rows = []
        for spec in sec["fields"]:
            fname = f"{prefix}{spec['key']}"
            if fname in extra_form.fields:
                rows.append({"spec": spec, "field": extra_form[fname]})
        if rows:
            by_section.append({"title": sec["title"], "rows": rows})
    return {
        "form_schema": fs,
        "extra_form": extra_form,
        "form_sections": sections,
        "extra_fields_by_section": by_section,
        "extra_display": [
            (f.get("label", f["key"]), (case.extra_data or {}).get(f["key"], ""))
            for f in schema
            if f.get("type") != "section" and (case.extra_data or {}).get(f["key"], "")
        ],
    }


def save_case_extra_data(case, extra_form, schema: list, *, prefix="extra_"):
    merged = dict(case.extra_data or {})
    merged.update(extract_schema_values(extra_form, schema, prefix=prefix))
    case.extra_data = merged
    case.save(update_fields=["extra_data", "updated_at"])
