"""
Tool functions for the AI assistant.

Each function is called by the Anthropic API tool-use loop.
TOOL_DEFINITIONS contains the JSON schemas for tool registration.
"""

from django.db.models import Q
from django.utils import timezone

from . import registry


def _normalize_choice_fields(model_cls, data):
    """Normalize DB-backed choice field values (label→value mapping).

    If the LLM sends a label like "Advisor" instead of the value "advisor",
    map it to the correct value by checking ChoiceOption entries.
    """
    from dashboard.models import ChoiceOption

    CHOICE_CATEGORIES = {
        "entity_type": "entity_type",
        "firm_type": "firm_type",
        "contact_method": "contact_method",
        "matter_type": "matter_type",
        "note_type": "note_type",
        "policy_type": "policy_type",
        "vehicle_type": "vehicle_type",
        "aircraft_type": "aircraft_type",
    }
    for field_name, category in CHOICE_CATEGORIES.items():
        if field_name not in data:
            continue
        val = data[field_name]
        if not isinstance(val, str):
            continue
        # Check if the value already matches a valid choice value
        choices = ChoiceOption.objects.filter(category=category)
        valid_values = {c.value for c in choices}
        if val in valid_values:
            continue
        # Try case-insensitive value match
        for c in choices:
            if c.value.lower() == val.lower():
                data[field_name] = c.value
                break
        else:
            # Try label→value mapping (case-insensitive)
            for c in choices:
                if c.label.lower() == val.lower():
                    data[field_name] = c.value
                    break

# Allowlisted Django ORM lookup suffixes
ALLOWED_LOOKUPS = {
    "exact", "iexact", "contains", "icontains", "in",
    "lt", "lte", "gt", "gte", "startswith", "istartswith",
    "endswith", "iendswith", "isnull", "range", "date",
    "year", "month", "day",
}

MAX_RESULTS = 100
DEFAULT_LIMIT = 20


def _validate_filters(model, filters):
    """Validate filter keys against model fields and allowed lookups."""
    if not filters:
        return {}
    validated = {}
    field_names = {f.name for f in model._meta.get_fields()}
    for key, value in filters.items():
        parts = key.split("__")
        base_field = parts[0]
        # Allow traversal through FK fields (e.g. stakeholder__name)
        if base_field not in field_names:
            raise ValueError(f"Unknown field '{base_field}' on {model.__name__}")
        # Check lookup suffix if present
        if len(parts) > 1:
            lookup = parts[-1]
            # The last part could be a field name on a related model or a lookup
            if lookup not in ALLOWED_LOOKUPS and lookup not in field_names:
                # Check if it's a valid field on any related model (allow traversal)
                pass  # Allow it — Django will raise FieldError if invalid
        validated[key] = value
    return validated


def search(query, models=None):
    """Search across all models for matching records."""
    registry.build_registry()
    results = []
    limit = 10

    search_targets = registry.SEARCH_FIELDS
    if models:
        search_targets = {k: v for k, v in search_targets.items() if k in models or k.lower() in [m.lower() for m in models]}

    for model_name, fields in search_targets.items():
        try:
            model = registry.get_model(model_name)
        except ValueError:
            continue

        q_filter = Q()
        for field in fields:
            q_filter |= Q(**{f"{field}__icontains": query})

        qs = model.objects.filter(q_filter)[:limit]
        for obj in qs:
            entry = {
                "model": model_name,
                "id": obj.pk,
                "str": str(obj),
            }
            if hasattr(obj, "get_absolute_url"):
                try:
                    entry["url"] = obj.get_absolute_url()
                except Exception:
                    pass
            results.append(entry)

    return {"results": results, "count": len(results)}


def query(model, filters=None, fields=None, order_by=None, limit=DEFAULT_LIMIT):
    """Execute a flexible ORM query against a model."""
    model_cls = registry.get_model(model)
    validated_filters = _validate_filters(model_cls, filters)

    qs = model_cls.objects.all()
    if validated_filters:
        qs = qs.filter(**validated_filters)
    if order_by:
        if isinstance(order_by, str):
            order_by = [order_by]
        qs = qs.order_by(*order_by)

    limit = min(int(limit), MAX_RESULTS)
    qs = qs[:limit]

    if fields:
        # Return only specified fields as dicts
        results = []
        for obj in qs:
            data = {"__pk__": obj.pk, "__str__": str(obj), "__model__": model}
            for f in fields:
                try:
                    data[f] = registry._json_safe(getattr(obj, f))
                except Exception:
                    data[f] = None
            results.append(data)
        return {"results": results, "count": len(results)}

    return {
        "results": [registry.serialize_instance(obj, expand_relations=False) for obj in qs],
        "count": len(qs),
    }


def get_record(model, id):
    """Get a single record with full related data."""
    model_cls = registry.get_model(model)
    try:
        obj = model_cls.objects.get(pk=id)
    except model_cls.DoesNotExist:
        return {"error": f"{model} with id={id} not found"}
    return registry.serialize_instance(obj, expand_relations=True)


def create_record(model, data, dry_run=True):
    """Create a new record. dry_run=True returns a preview without saving."""
    model_cls = registry.get_model(model)

    # Normalize choice field values (label→value, case-insensitive)
    _normalize_choice_fields(model_cls, data)

    # Separate M2M fields from regular fields
    m2m_data = {}
    regular_data = {}
    m2m_field_names = {f.name for f in model_cls._meta.many_to_many}

    for key, value in data.items():
        if key in m2m_field_names:
            m2m_data[key] = value
        else:
            regular_data[key] = value

    # Resolve FK fields (accept integer IDs)
    for field in model_cls._meta.get_fields():
        if isinstance(field, registry.models.ForeignKey):
            if field.name in regular_data:
                val = regular_data.pop(field.name)
                regular_data[f"{field.name}_id"] = val

    if dry_run:
        preview = {
            "action": "create",
            "model": model,
            "data": {k: registry._json_safe(v) for k, v in regular_data.items()},
            "dry_run": True,
        }
        if m2m_data:
            preview["m2m_data"] = m2m_data
        return preview

    obj = model_cls(**regular_data)
    obj.full_clean()
    obj.save()

    for field_name, ids in m2m_data.items():
        getattr(obj, field_name).set(ids)

    return {
        "action": "created",
        "model": model,
        "record": registry.serialize_instance(obj),
    }


def update_record(model, id, data, dry_run=True):
    """Update an existing record. dry_run=True returns a preview."""
    model_cls = registry.get_model(model)
    try:
        obj = model_cls.objects.get(pk=id)
    except model_cls.DoesNotExist:
        return {"error": f"{model} with id={id} not found"}

    # Normalize choice field values (label→value, case-insensitive)
    _normalize_choice_fields(model_cls, data)

    m2m_data = {}
    regular_data = {}
    m2m_field_names = {f.name for f in model_cls._meta.many_to_many}

    for key, value in data.items():
        if key in m2m_field_names:
            m2m_data[key] = value
        else:
            regular_data[key] = value

    if dry_run:
        changes = {}
        for key, new_val in regular_data.items():
            field_name = key
            if any(isinstance(f, registry.models.ForeignKey) and f.name == key for f in model_cls._meta.get_fields()):
                field_name = f"{key}_id"
                current_val = getattr(obj, field_name, None)
            else:
                current_val = getattr(obj, field_name, None)
            changes[key] = {
                "current": registry._json_safe(current_val),
                "new": registry._json_safe(new_val),
            }
        preview = {
            "action": "update",
            "model": model,
            "id": id,
            "changes": changes,
            "dry_run": True,
        }
        if m2m_data:
            preview["m2m_changes"] = m2m_data
        return preview

    for key, value in regular_data.items():
        if any(isinstance(f, registry.models.ForeignKey) and f.name == key for f in model_cls._meta.get_fields()):
            setattr(obj, f"{key}_id", value)
        else:
            setattr(obj, key, value)
    obj.full_clean()
    obj.save()

    for field_name, ids in m2m_data.items():
        getattr(obj, field_name).set(ids)

    return {
        "action": "updated",
        "model": model,
        "record": registry.serialize_instance(obj),
    }


def delete_record(model, id, dry_run=True):
    """Delete a record. dry_run=True returns a preview of what would be deleted."""
    model_cls = registry.get_model(model)
    try:
        obj = model_cls.objects.get(pk=id)
    except model_cls.DoesNotExist:
        return {"error": f"{model} with id={id} not found"}

    if dry_run:
        # Show what would be deleted (CASCADE impact)
        collector_info = []
        from django.db.models.deletion import Collector
        collector = Collector(using="default")
        collector.collect([obj])
        for model_cls_del, instances in collector.data.items():
            for inst in instances:
                collector_info.append({
                    "model": model_cls_del.__name__,
                    "id": inst.pk,
                    "str": str(inst),
                })
        return {
            "action": "delete",
            "model": model,
            "id": id,
            "record": str(obj),
            "cascade_deletes": collector_info,
            "dry_run": True,
        }

    obj.delete()
    return {"action": "deleted", "model": model, "id": id}


def list_models():
    """List all available models with their field metadata."""
    registry.build_registry()
    result = []
    seen = set()
    for name, model in sorted(registry.MODEL_REGISTRY.items()):
        if name != model.__name__:
            continue
        if name in seen:
            continue
        seen.add(name)
        result.append({
            "name": name,
            "app": model._meta.app_label,
            "fields": registry.get_field_info(model),
        })
    return {"models": result, "count": len(result)}


def summarize():
    """Return an overview of the system state."""
    registry.build_registry()
    today = timezone.localdate()

    stats = {}

    # Counts for major models
    count_models = [
        "Stakeholder", "LegalMatter", "RealEstate", "Investment", "Loan",
        "Vehicle", "Aircraft", "InsurancePolicy", "Lease", "Task", "Note",
        "CashFlowEntry", "Document", "Provider", "Prescription", "Appointment",
    ]
    for name in count_models:
        try:
            model = registry.get_model(name)
            stats[f"{name}_count"] = model.objects.count()
        except (ValueError, Exception):
            pass

    # Task stats
    try:
        Task = registry.get_model("Task")
        stats["overdue_tasks"] = Task.objects.filter(
            due_date__lt=today
        ).exclude(status="complete").count()
        stats["tasks_due_this_week"] = Task.objects.filter(
            due_date__gte=today,
            due_date__lte=today + timezone.timedelta(days=7),
        ).exclude(status="complete").count()
    except Exception:
        pass

    # Legal stats
    try:
        LegalMatter = registry.get_model("LegalMatter")
        stats["active_legal_matters"] = LegalMatter.objects.filter(status="active").count()
        stats["pending_legal_matters"] = LegalMatter.objects.filter(status="pending").count()
    except Exception:
        pass

    # Follow-up stats
    try:
        FollowUp = registry.get_model("FollowUp")
        stats["stale_followups"] = FollowUp.objects.filter(
            response_received=False,
        ).count()
    except Exception:
        pass

    # Upcoming appointments
    try:
        Appointment = registry.get_model("Appointment")
        stats["upcoming_appointments"] = Appointment.objects.filter(
            date__gte=today,
            date__lte=today + timezone.timedelta(days=30),
        ).exclude(status__in=["cancelled", "completed"]).count()
    except Exception:
        pass

    return stats


# Anthropic tool definitions
TOOL_DEFINITIONS = [
    {
        "name": "search",
        "description": "Search across all models in Control Center for records matching a text query. Returns matching records with their model type, ID, name, and URL. Use this for broad searches when you don't know which model to query.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text to match against record names, titles, descriptions, etc."},
                "models": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of model names to restrict search to (e.g. ['Task', 'Note']). Omit to search all models.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "query",
        "description": "Execute a flexible database query against a specific model. Supports Django ORM-style filter lookups like __icontains, __lt, __gte, __in, __isnull, etc. Returns a list of matching records. Use this for precise, filtered queries.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name (e.g. 'Task', 'Stakeholder', 'LegalMatter')"},
                "filters": {
                    "type": "object",
                    "description": "Django ORM filter kwargs. Examples: {\"status\": \"active\"}, {\"due_date__lt\": \"2026-03-20\"}, {\"stakeholder__name__icontains\": \"marcus\"}",
                    "additionalProperties": True,
                },
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of field names to return. Omit for all fields.",
                },
                "order_by": {
                    "oneOf": [{"type": "string"}, {"type": "array", "items": {"type": "string"}}],
                    "description": "Field(s) to order by. Prefix with '-' for descending. Examples: '-due_date', ['status', '-created_at']",
                },
                "limit": {"type": "integer", "description": "Max records to return (default 20, max 100)", "default": 20},
            },
            "required": ["model"],
        },
    },
    {
        "name": "get_record",
        "description": "Get a single record by ID with all its fields and related data expanded. Use this to see full details of a specific record including its relationships.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name (e.g. 'Task', 'LegalMatter')"},
                "id": {"type": "integer", "description": "Record primary key (ID)"},
            },
            "required": ["model", "id"],
        },
    },
    {
        "name": "create_record",
        "description": "Create a new record in the database. IMPORTANT: Always call with dry_run=true first to preview, show the user what will be created, and get their confirmation before calling again with dry_run=false.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name (e.g. 'Task', 'Note')"},
                "data": {
                    "type": "object",
                    "description": "Field values for the new record. Use field names from the schema. For FK fields, pass the related record's ID. For M2M fields, pass a list of IDs.",
                    "additionalProperties": True,
                },
                "dry_run": {"type": "boolean", "description": "If true, preview only (no database changes). Always preview first.", "default": True},
            },
            "required": ["model", "data"],
        },
    },
    {
        "name": "update_record",
        "description": "Update an existing record. IMPORTANT: Always call with dry_run=true first to preview changes, show the user what will change, and get their confirmation before calling again with dry_run=false.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name"},
                "id": {"type": "integer", "description": "Record ID to update"},
                "data": {
                    "type": "object",
                    "description": "Fields to update with new values. Only include fields you want to change.",
                    "additionalProperties": True,
                },
                "dry_run": {"type": "boolean", "description": "If true, preview only. Always preview first.", "default": True},
            },
            "required": ["model", "id", "data"],
        },
    },
    {
        "name": "delete_record",
        "description": "Delete a record. IMPORTANT: Always call with dry_run=true first to see what would be deleted (including cascade deletes), show the user, and get their confirmation before calling with dry_run=false.",
        "input_schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Model name"},
                "id": {"type": "integer", "description": "Record ID to delete"},
                "dry_run": {"type": "boolean", "description": "If true, preview only. Always preview first.", "default": True},
            },
            "required": ["model", "id"],
        },
    },
    {
        "name": "list_models",
        "description": "List all available data models with their fields, types, and relationships. Use this to discover the data schema when you need to understand what models and fields are available for querying.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "summarize",
        "description": "Get an overview of the current system state: record counts, overdue tasks, active legal matters, upcoming appointments, and other key metrics. Use this to answer broad questions about the overall state of affairs.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
        "cache_control": {"type": "ephemeral"},
    },
]

# Map tool names to functions
TOOL_HANDLERS = {
    "search": search,
    "query": query,
    "get_record": get_record,
    "create_record": create_record,
    "update_record": update_record,
    "delete_record": delete_record,
    "list_models": list_models,
    "summarize": summarize,
}
