"""
Model registry for the AI assistant.

Maps model names to Django model classes and provides serialization
and schema introspection for the Anthropic tool interface.
"""

import datetime
from decimal import Decimal

from django.db import models
from django.forms.models import model_to_dict

MODEL_REGISTRY = {}
_registry_built = False

# Apps to include in the registry
INCLUDED_APPS = [
    "stakeholders",
    "assets",
    "legal",
    "tasks",
    "cashflow",
    "notes",
    "healthcare",
    "documents",
    "checklists",
    "dashboard",
    "email_links",
]

# Search field mappings: model name -> list of text fields to search
SEARCH_FIELDS = {
    "Stakeholder": ["name", "organization", "notes_text"],
    "Task": ["title", "description"],
    "Note": ["title", "content"],
    "LegalMatter": ["title", "case_number", "description"],
    "RealEstate": ["name", "address"],
    "Investment": ["name"],
    "Loan": ["name"],
    "CashFlowEntry": ["description"],
    "Lease": ["name"],
    "Document": ["title", "description", "category"],
    "EmailLink": ["subject", "from_name", "from_email"],
    "Provider": ["name", "specialty", "practice_name"],
    "Prescription": ["medication_name", "generic_name"],
    "Appointment": ["title", "purpose"],
    "Evidence": ["title", "description"],
    "Vehicle": ["name", "make", "model_name"],
    "Aircraft": ["name", "make", "model_name"],
    "InsurancePolicy": ["name", "policy_number"],
    "Condition": ["name"],
    "Tag": ["name"],
    "Folder": ["name"],
    "ScratchPad": ["title", "content", "participants_text"],
    "Checklist": ["name"],
    "ChecklistItem": ["title"],
    "FollowUp": ["notes_text", "response_notes"],
    "ContactLog": ["summary"],
    "LegalCommunication": ["subject", "summary"],
    "CaseLog": ["text"],
    "FirmEngagement": ["scope", "notes"],
    "Visit": ["reason", "summary"],
    "Supplement": ["name"],
    "TestResult": ["test_name"],
    "Advice": ["title", "advice_text"],
}


def build_registry():
    """Populate MODEL_REGISTRY from all included apps."""
    global _registry_built
    if _registry_built:
        return

    from django.apps import apps

    for app_label in INCLUDED_APPS:
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            continue
        for model in app_config.get_models():
            name = model.__name__
            MODEL_REGISTRY[name] = model
            MODEL_REGISTRY[name.lower()] = model

    _registry_built = True


def get_model(name):
    """Look up a model by name (case-insensitive). Raises ValueError if not found."""
    build_registry()
    model = MODEL_REGISTRY.get(name) or MODEL_REGISTRY.get(name.lower())
    if model is None:
        available = sorted(set(k for k, v in MODEL_REGISTRY.items() if k == v.__name__))
        raise ValueError(
            f"Unknown model '{name}'. Available models: {', '.join(available)}"
        )
    return model


def _json_safe(value):
    """Convert a value to JSON-serializable form."""
    if value is None:
        return None
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def serialize_instance(instance, expand_relations=True):
    """
    Serialize a Django model instance to a JSON-serializable dict.

    Includes metadata: __model__, __str__, __url__, __pk__.
    FK fields become {id, str} dicts. M2M fields become lists of {id, str}.
    """
    data = model_to_dict(instance)
    result = {
        "__model__": instance.__class__.__name__,
        "__pk__": instance.pk,
        "__str__": str(instance),
    }
    if hasattr(instance, "get_absolute_url"):
        try:
            result["__url__"] = instance.get_absolute_url()
        except Exception:
            pass

    opts = instance.__class__._meta

    for field in opts.get_fields():
        name = field.name

        if isinstance(field, (models.ManyToManyField, models.ManyToManyRel, models.ManyToOneRel)):
            if expand_relations:
                accessor = field.get_accessor_name() if hasattr(field, "get_accessor_name") else name
                m2m_limit = 10
                try:
                    manager = getattr(instance, accessor)
                    # Fetch limit+1 to detect truncation without an extra count query
                    items = list(manager.all()[:m2m_limit + 1])
                    truncated = len(items) > m2m_limit
                    result[accessor] = [
                        {"id": obj.pk, "str": str(obj)} for obj in items[:m2m_limit]
                    ]
                    if truncated:
                        result[f"{accessor}_truncated"] = True
                except Exception:
                    pass
            continue

        if isinstance(field, models.ForeignKey):
            fk_id = getattr(instance, f"{name}_id", None)
            if expand_relations and fk_id is not None:
                try:
                    related_obj = getattr(instance, name)
                    result[name] = {"id": fk_id, "str": str(related_obj)}
                except Exception:
                    result[name] = {"id": fk_id, "str": None}
            else:
                result[name] = fk_id
            continue

        if name in data:
            result[name] = _json_safe(data[name])
        else:
            try:
                result[name] = _json_safe(getattr(instance, name, None))
            except Exception:
                pass

    return result


def get_field_info(model):
    """Return field metadata for a model as a list of dicts."""
    fields = []
    for field in model._meta.get_fields():
        info = {"name": field.name}

        if isinstance(field, (models.ManyToOneRel, models.ManyToManyRel)):
            continue

        if isinstance(field, models.ForeignKey):
            info["type"] = f"fk -> {field.related_model.__name__}"
            info["required"] = not field.null
        elif isinstance(field, models.ManyToManyField):
            through = ""
            if field.remote_field.through and not field.remote_field.through._meta.auto_created:
                through = f" through {field.remote_field.through.__name__}"
            info["type"] = f"m2m -> {field.related_model.__name__}{through}"
            info["required"] = False
        elif isinstance(field, models.CharField):
            info["type"] = f"string(max={field.max_length})"
            info["required"] = not field.blank
            if field.choices:
                info["choices"] = [c[0] for c in field.choices]
        elif isinstance(field, models.TextField):
            info["type"] = "text"
            info["required"] = not field.blank
        elif isinstance(field, (models.IntegerField, models.PositiveIntegerField, models.PositiveSmallIntegerField)):
            info["type"] = "integer"
            info["required"] = not (field.null or field.has_default())
        elif isinstance(field, models.DecimalField):
            info["type"] = f"decimal({field.max_digits},{field.decimal_places})"
            info["required"] = not field.null
        elif isinstance(field, models.BooleanField):
            info["type"] = "boolean"
            info["required"] = False
        elif isinstance(field, models.DateTimeField):
            if field.auto_now or field.auto_now_add:
                continue  # skip auto timestamps
            info["type"] = "datetime"
            info["required"] = not field.null
        elif isinstance(field, models.DateField):
            info["type"] = "date"
            info["required"] = not field.null
        elif isinstance(field, models.TimeField):
            info["type"] = "time"
            info["required"] = not field.null
        elif isinstance(field, models.FileField):
            info["type"] = "file"
            info["required"] = not field.blank
        elif isinstance(field, models.URLField):
            info["type"] = "url"
            info["required"] = not field.blank
        elif isinstance(field, models.EmailField):
            info["type"] = "email"
            info["required"] = not field.blank
        elif isinstance(field, models.JSONField):
            info["type"] = "json"
            info["required"] = False
        elif isinstance(field, models.SlugField):
            info["type"] = f"slug(max={field.max_length})"
            info["required"] = not field.blank
        elif isinstance(field, models.AutoField) or isinstance(field, models.BigAutoField):
            info["type"] = "auto_id"
            info["required"] = False
        else:
            info["type"] = field.get_internal_type()
            info["required"] = not getattr(field, "null", True)

        fields.append(info)

    return fields


def get_schema_text():
    """Generate a compact text schema for the system prompt."""
    build_registry()
    lines = []
    seen = set()

    for name, model in sorted(MODEL_REGISTRY.items()):
        if name != model.__name__:
            continue  # skip lowercase aliases
        if name in seen:
            continue
        seen.add(name)

        app_label = model._meta.app_label
        lines.append(f"\n## {app_label}.{name}")

        for fi in get_field_info(model):
            parts = [f"  - {fi['name']}: {fi['type']}"]
            if fi.get("required"):
                parts.append("(required)")
            if fi.get("choices"):
                choices_str = ", ".join(str(c) for c in fi["choices"][:10])
                parts.append(f"[{choices_str}]")
            lines.append(" ".join(parts))

    return "\n".join(lines)
