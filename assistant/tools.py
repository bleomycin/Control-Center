"""
Tool functions for the AI assistant.

Each function is called by the Anthropic API tool-use loop.
TOOL_DEFINITIONS contains the JSON schemas for tool registration.
"""

from django.db.models import Q
from django.utils import timezone

from documents.services import bulk_link_drive_files as _service_bulk_link_drive_files

from . import registry


def _apply_reminder_policy(model_cls, data, existing_obj=None):
    """Enforce server-side reminder policy for Task records.

    - Meetings: strip reminder_date (calendar feed owns meeting reminders).
    - Non-meetings with due_date + due_time and no explicit reminder_date:
      auto-compute reminder_date from AssistantSettings.default_reminder_minutes.
    """
    if model_cls.__name__ != "Task":
        return

    task_type = data.get("task_type")
    if task_type is None and existing_obj is not None:
        task_type = existing_obj.task_type

    if task_type == "meeting":
        data.pop("reminder_date", None)
    elif "reminder_date" not in data:
        due_date = data.get("due_date")
        due_time = data.get("due_time")
        if due_date and due_time:
            from assistant.models import AssistantSettings
            from django.utils import timezone as _tz
            from django.utils.dateparse import parse_date, parse_time
            from datetime import datetime as _dt, timedelta as _td

            mins = AssistantSettings.load().default_reminder_minutes
            if mins:
                d = due_date if hasattr(due_date, "year") else parse_date(str(due_date))
                t = due_time if hasattr(due_time, "hour") else parse_time(str(due_time))
                if d and t:
                    aware = _tz.make_aware(_dt.combine(d, t), _tz.get_current_timezone())
                    # ISO string, not datetime: this dict is aliased into
                    # block.input, which gets saved to ChatMessage.tool_data
                    # (JSONField) and re-sent as Anthropic message history.
                    data["reminder_date"] = (aware - _td(minutes=mins)).isoformat()


def _normalize_choice_fields(model_cls, data):
    """Normalize DB-backed choice field values (label→value mapping).

    If the LLM sends a label like "Advisor" instead of the value "advisor",
    map it to the correct value by checking cached ChoiceOption entries.
    """
    from dashboard.choices import get_choices

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
        # get_choices returns cached [(value, label), ...] tuples
        choices = get_choices(category)
        valid_values = {v for v, _l in choices}
        if val in valid_values:
            continue
        # Try case-insensitive value match
        for v, _l in choices:
            if v.lower() == val.lower():
                data[field_name] = v
                break
        else:
            # Try label→value mapping (case-insensitive)
            for v, label in choices:
                if label.lower() == val.lower():
                    data[field_name] = v
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


ENRICH_THRESHOLD = 10  # Auto-enrich search results when total count is ≤ this

# Key fields to include per model when enriching search results.
# These give the model enough context to make connections without get_record.
ENRICH_FIELDS = {
    "Stakeholder": {
        "scalars": ["entity_type", "organization", "phone", "email",
                     "address", "city", "state"],
    },
    "RealEstate": {
        "scalars": ["address", "city", "state", "property_type",
                     "estimated_value", "status"],
    },
    "Aircraft": {
        "scalars": ["registration_number", "make", "model_name", "year"],
        "reverse": ["owners"],
    },
    "Vehicle": {
        "scalars": ["year", "make", "model_name", "vin"],
        "reverse": ["owners"],
    },
    "Investment": {
        "scalars": ["investment_type", "total_committed"],
    },
    "Loan": {
        "scalars": ["loan_type", "original_amount", "lender"],
        "reverse": ["parties"],
    },
    "LegalMatter": {
        "scalars": ["matter_type", "status"],
        "m2m": ["attorneys"],
    },
    "Task": {
        "scalars": ["status", "priority", "due_date", "due_time",
                     "task_type", "direction", "location"],
        "fk": ["assigned_to"],
    },
    "InsurancePolicy": {
        "scalars": ["policy_type", "policy_number", "premium", "status"],
    },
    "Note": {
        "scalars": ["note_type", "date"],
    },
    "Lease": {
        "scalars": ["lease_type", "status", "start_date", "end_date"],
    },
}


def _enrich_result(obj, model_name):
    """Add key fields to a search result for richer context."""
    spec = ENRICH_FIELDS.get(model_name)
    if not spec:
        return None

    details = {}

    # Scalar fields (direct attributes)
    for field_name in spec.get("scalars", []):
        val = getattr(obj, field_name, None)
        if val is not None and val != "":
            details[field_name] = registry._json_safe(val)

    # FK fields (show id + str)
    for field_name in spec.get("fk", []):
        related = getattr(obj, field_name, None)
        if related:
            details[field_name] = {"id": related.pk, "str": str(related)}

    # M2M fields (show list of id + str, limit 5)
    for field_name in spec.get("m2m", []):
        try:
            manager = getattr(obj, field_name)
            items = list(manager.all()[:5])
            if items:
                details[field_name] = [
                    {"id": o.pk, "str": str(o)} for o in items
                ]
        except Exception:
            pass

    # Reverse relations (e.g., aircraft_owners → through model)
    for accessor in spec.get("reverse", []):
        try:
            manager = getattr(obj, accessor)
            items = list(manager.select_related("stakeholder").all()[:5])
            if items:
                details[accessor] = [
                    {"id": o.stakeholder_id, "str": str(o.stakeholder),
                     "role": getattr(o, "role", "")}
                    for o in items if hasattr(o, "stakeholder")
                ]
        except Exception:
            pass

    return details if details else None


def _build_word_filter(fields, query):
    """Build a Q filter: AND all query words within each field, OR across fields.

    "Stan Gribble" on field "name" becomes:
        (name__icontains="Stan" AND name__icontains="Gribble")

    This matches "Stanley W. Gribble" — the old single-substring approach did not.
    """
    words = query.split()
    if not words:
        return Q()
    q_filter = Q()
    for field in fields:
        field_q = Q()
        for word in words:
            field_q &= Q(**{f"{field}__icontains": word})
        q_filter |= field_q
    return q_filter


# Fields that represent body/notes content rather than entity identity.
# Name matches on these are deprioritized (searched in pass 2) so that
# a record mentioning "Stan Gribble" in notes doesn't crowd out
# the actual "Stanley W. Gribble" record matched by name.
_SECONDARY_FIELDS = frozenset({
    "notes_text",
    "description",
    "content",
    "notes",
    "summary",
    "advice_text",
    "response_notes",
    "text",
    "scope",
    "participants_text",
    "purpose",
})


def search(query, models=None):
    """Search across all models for matching records.

    Uses word-splitting (AND within field, OR across fields) so that
    "Stan Gribble" matches "Stanley W. Gribble".

    Primary fields (name, title) are searched first; secondary fields
    (notes_text, description) fill remaining slots. This prevents
    notes-text mentions from burying direct name matches.
    """
    registry.build_registry()
    if not query or not query.strip():
        return {"results": [], "count": 0}

    results = []
    seen_keys = set()
    model_counts = {}
    per_model_limit = 10
    max_total = 50

    search_targets = registry.SEARCH_FIELDS
    if models:
        search_targets = {k: v for k, v in search_targets.items() if k in models or k.lower() in [m.lower() for m in models]}

    def _collect(model_name, model, fields):
        """Query one model on the given fields and append unique results."""
        if not fields:
            return
        current = model_counts.get(model_name, 0)
        model_remaining = per_model_limit - current
        global_remaining = max_total - len(results)
        limit = min(model_remaining, global_remaining)
        if limit <= 0:
            return

        q_filter = _build_word_filter(fields, query)
        qs = model.objects.filter(q_filter)
        # Exclude PKs already found for this model to avoid fetching dupes
        found_pks = [pk for (mn, pk) in seen_keys if mn == model_name]
        if found_pks:
            qs = qs.exclude(pk__in=found_pks)
        for obj in qs[:limit]:
            key = (model_name, obj.pk)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            model_counts[model_name] = model_counts.get(model_name, 0) + 1
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
            entry["_obj"] = obj
            entry["_model_name"] = model_name
            results.append(entry)

    # Pass 1: primary fields (name, title, etc.) — identity matches first
    for model_name, fields in search_targets.items():
        if len(results) >= max_total:
            break
        try:
            model = registry.get_model(model_name)
        except ValueError:
            continue
        primary = [f for f in fields if f not in _SECONDARY_FIELDS]
        _collect(model_name, model, primary)

    # Pass 2: secondary fields (notes_text, description) — fill remaining slots
    for model_name, fields in search_targets.items():
        if len(results) >= max_total:
            break
        try:
            model = registry.get_model(model_name)
        except ValueError:
            continue
        secondary = [f for f in fields if f in _SECONDARY_FIELDS]
        _collect(model_name, model, secondary)

    # Enrich with key fields when result set is small
    if len(results) <= ENRICH_THRESHOLD:
        for entry in results:
            details = _enrich_result(entry.pop("_obj"), entry.pop("_model_name"))
            if details:
                entry["details"] = details
    else:
        for entry in results:
            entry.pop("_obj", None)
            entry.pop("_model_name", None)

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
    qs = model_cls.objects.all()

    # Auto-discover FK and M2M fields to eliminate N+1 queries
    fk_fields = [
        f.name for f in model_cls._meta.get_fields()
        if isinstance(f, registry.models.ForeignKey)
    ]
    m2m_fields = [
        f.name for f in model_cls._meta.get_fields()
        if isinstance(f, registry.models.ManyToManyField)
    ]
    if fk_fields:
        qs = qs.select_related(*fk_fields)
    if m2m_fields:
        qs = qs.prefetch_related(*m2m_fields)

    try:
        obj = qs.get(pk=id)
    except model_cls.DoesNotExist:
        return {"error": f"{model} with id={id} not found"}
    return registry.serialize_instance(obj, expand_relations=True)


def create_record(model, data, dry_run=True):
    """Create a new record. dry_run=True returns a preview without saving."""
    model_cls = registry.get_model(model)

    # Normalize choice field values (label→value, case-insensitive)
    _normalize_choice_fields(model_cls, data)
    _apply_reminder_policy(model_cls, data)

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
    _apply_reminder_policy(model_cls, data, existing_obj=obj)

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


def bulk_link_drive_files(entity_type, entity_id, files, dry_run=True):
    """Create Document records and link them to a target entity in a single batch.

    Wraps documents.services.bulk_link_drive_files. Defaults dry_run=True so the
    assistant always previews first (matches the system prompt rule #1).
    """
    return _service_bulk_link_drive_files(
        entity_type=entity_type,
        entity_id=entity_id,
        files=files,
        dry_run=dry_run,
    )


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
    """Return an overview of the system state.

    Uses batched raw SQL for model counts (1 query instead of 16)
    and individual filtered queries only where needed.
    """
    registry.build_registry()
    today = timezone.localdate()

    stats = {}

    # Batch all simple model counts into a single raw SQL query
    count_models = [
        "Stakeholder", "LegalMatter", "RealEstate", "Investment", "Loan",
        "Vehicle", "Aircraft", "InsurancePolicy", "Lease", "Task", "Note",
        "CashFlowEntry", "Document", "Provider", "Prescription", "Appointment",
    ]
    table_map = {}  # table_name -> display_name
    for name in count_models:
        try:
            model = registry.get_model(name)
            table_map[model._meta.db_table] = name
        except (ValueError, Exception):
            pass

    if table_map:
        from django.db import connection
        # Build a UNION ALL query for all model counts in one round-trip
        parts = [f"SELECT '{name}' AS name, COUNT(*) AS cnt FROM \"{table}\""
                 for table, name in table_map.items()]
        sql = " UNION ALL ".join(parts)
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql)
                for row in cursor.fetchall():
                    stats[f"{row[0]}_count"] = row[1]
        except Exception:
            # Fallback to individual counts if raw SQL fails
            for name in count_models:
                try:
                    model = registry.get_model(name)
                    stats[f"{name}_count"] = model.objects.count()
                except (ValueError, Exception):
                    pass

    # Task stats (2 filtered queries — hard to batch further)
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


def read_email(id):
    """Fetch full email thread content for a linked EmailLink record."""
    from email_links.models import EmailLink
    from email_links import gmail
    from .views import _strip_quoted_reply, _strip_boilerplate

    try:
        el = EmailLink.objects.get(pk=id)
    except EmailLink.DoesNotExist:
        return {"error": f"EmailLink with id={id} not found"}

    if not gmail.is_available():
        return {"error": "Gmail is not connected"}

    messages = gmail.get_thread_messages(el.message_id)
    if messages is None:
        return {"error": "Failed to fetch thread from Gmail"}

    parts = [f"Subject: {el.subject}", f"Thread: {len(messages)} message(s)"]
    entities = el.linked_entities
    if entities:
        parts.append("Linked to: " + ", ".join(f"{label}: {obj}" for label, obj in entities))
    parts.append("")

    for i, msg in enumerate(messages, 1):
        parts.append(f"--- Message {i} ---")
        parts.append(f"From: {msg.get('from_name', '')} <{msg.get('from_email', '')}>")
        parts.append(f"Date: {msg.get('date', '')}")
        body = _strip_boilerplate(_strip_quoted_reply(msg.get("body", "").strip()))
        parts.append(body)
        parts.append("")

    return {"content": "\n".join(parts)}


def read_document(id, offset=0):
    """Fetch the text content of a linked Document (Drive or local file).

    Pass `offset` to resume past a prior truncation cut-off. The returned
    envelope includes `total_chars`, `offset`, and (when truncated)
    `next_offset` so the caller can paginate.
    """
    from documents.models import Document
    from documents import extract, gdrive

    try:
        doc = Document.objects.get(pk=id)
    except Document.DoesNotExist:
        return {"error": f"Document with id={id} not found"}

    if doc.gdrive_file_id:
        if not gdrive.is_connected():
            return {"error": "Google Drive is not connected"}
        result = extract.extract_text_from_drive(
            doc.gdrive_file_id, doc.gdrive_mime_type, offset=offset,
        )
    elif doc.file:
        result = extract.extract_text_from_local(doc.file.path, offset=offset)
    else:
        return {"error": "Document has no file content (no Drive link or local upload)"}

    if "error" in result:
        return result

    parts = [f"Title: {doc.title}"]
    if doc.gdrive_file_name:
        parts.append(f"Filename: {doc.gdrive_file_name}")
    if doc.category:
        parts.append(f"Category: {doc.category}")
    if doc.description:
        parts.append(f"Description: {doc.description}")
    entities = doc.linked_entities
    if entities:
        parts.append(
            "Linked to: " + ", ".join(f"{label}: {obj}" for label, obj in entities),
        )
    if result.get("warning"):
        parts.append(f"Warning: {result['warning']}")
    if result.get("truncated"):
        parts.append(
            f"Notice: Showing chars {result.get('offset', 0)}–"
            f"{result.get('next_offset')} of {result.get('total_chars')}. "
            f"Content past char {result.get('next_offset')} was NOT read. "
            f"Call read_document again with offset={result.get('next_offset')} to continue."
        )
    parts.append("")
    parts.append(result.get("text", ""))

    envelope = {
        "content": "\n".join(parts),
        "truncated": result.get("truncated", False),
        "total_chars": result.get("total_chars", 0),
        "offset": result.get("offset", 0),
    }
    next_offset = result.get("next_offset")
    if next_offset is not None:
        envelope["next_offset"] = next_offset
    return envelope


# Anthropic tool definitions
TOOL_DEFINITIONS = [
    {
        "name": "search",
        "strict": True,
        "description": "Search across all models in Control Center for records matching a text query. Returns matching records with their model type, ID, name, and URL. Use this for broad searches when you don't know which model to query.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
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
        "strict": True,
        "description": "Get a single record by ID with all its fields and related data expanded. Use this to see full details of a specific record including its relationships.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
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
        "strict": True,
        "description": "Delete a record. IMPORTANT: Always call with dry_run=true first to see what would be deleted (including cascade deletes), show the user, and get their confirmation before calling with dry_run=false.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "model": {"type": "string", "description": "Model name"},
                "id": {"type": "integer", "description": "Record ID to delete"},
                "dry_run": {"type": "boolean", "description": "If true, preview only. Always preview first.", "default": True},
            },
            "required": ["model", "id"],
        },
    },
    {
        "name": "bulk_link_drive_files",
        "description": (
            "Create Document records for one or more Google Drive files and link "
            "them to a single target entity in a single batch. Use this when the user "
            "has attached Drive files (you'll see an [AttachedDriveFiles] block in "
            "the user's message) and wants them linked to a property, stakeholder, "
            "investment, loan, lease, policy, vehicle, aircraft, or legal matter. "
            "IMPORTANT: Always call with dry_run=true first to preview, show the "
            "user the target entity and file list, and get their confirmation before "
            "calling again with dry_run=false. NEVER skip the preview step."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity_type": {
                    "type": "string",
                    "enum": [
                        "realestate", "investment", "loan", "lease", "policy",
                        "vehicle", "aircraft", "stakeholder", "legalmatter",
                    ],
                    "description": "The target entity type to link the files to.",
                },
                "entity_id": {
                    "type": "integer",
                    "description": "Primary key of the target entity. If you just created the entity, use the new pk returned by create_record.",
                },
                "files": {
                    "type": "array",
                    "description": "Drive files to link. Each item: {id, name, mimeType, url}. Pass the file list verbatim from the [AttachedDriveFiles] block in the user's message.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id":       {"type": "string", "description": "Google Drive file ID"},
                            "name":     {"type": "string", "description": "Filename (with extension)"},
                            "mimeType": {"type": "string", "description": "Drive MIME type"},
                            "url":      {"type": "string", "description": "Drive shareable URL"},
                        },
                        "required": ["id", "name", "mimeType", "url"],
                    },
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview only (no database changes). Always preview first.",
                    "default": True,
                },
            },
            "required": ["entity_type", "entity_id", "files"],
        },
    },
    {
        "name": "list_models",
        "strict": True,
        "description": "List all available data models with their fields, types, and relationships. Use this to discover the data schema when you need to understand what models and fields are available for querying.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    },
    {
        "name": "summarize",
        "strict": True,
        "description": "Get an overview of the current system state: record counts, overdue tasks, active legal matters, upcoming appointments, and other key metrics. Use this to answer broad questions about the overall state of affairs.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {},
        },
    },
    {
        "name": "read_email",
        "strict": True,
        "description": "Fetch the full content of a linked Gmail thread. Use when you find an EmailLink record whose subject suggests it may contain information relevant to the user's query. Returns all messages in the thread with sender, date, and body text.",
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "The EmailLink record ID (from search or query results)",
                },
            },
            "required": ["id"],
        },
    },
    {
        "name": "read_document",
        "strict": True,
        "description": (
            "Fetch the text content of a linked Document. Use when an entity has a "
            "`documents` relation containing a record whose title, filename, or "
            "category suggests it may answer the user's question. Supports PDF, "
            "DOCX, XLSX, Google Docs/Sheets/Slides, and plain text/CSV/markdown. "
            "Scanned PDFs and image-only documents return an empty body with a "
            "warning — surface that warning to the user verbatim. When in doubt, "
            "read the document — missing buried information is worse than reading "
            "an extra file.\n\n"
            "The response envelope includes `truncated`, `total_chars`, `offset`, "
            "and (when truncated) `next_offset`. If `truncated` is true, you only "
            "saw characters `offset`–`next_offset` of a `total_chars`-character "
            "document — content past the cutoff is NOT in your context. You MUST "
            "NOT cite, quote, paraphrase, or infer section numbers, clause text, "
            "exhibit contents, or any specifics from positions past the slice you "
            "read. If the user's question likely needs later content, re-call "
            "read_document with `offset=<next_offset>` to continue reading; "
            "otherwise tell the user the document was truncated and ask them to "
            "narrow the question."
        ),
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "The Document record ID (from search, query, or get_record results).",
                },
                "offset": {
                    "type": "integer",
                    "description": "Character offset to start reading from. Omit (or 0) to start at the beginning. Pass the `next_offset` from a prior truncated result to continue reading past the cutoff.",
                    "default": 0,
                },
            },
            "required": ["id"],
        },
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
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
    "bulk_link_drive_files": bulk_link_drive_files,
    "list_models": list_models,
    "summarize": summarize,
    "read_email": read_email,
    "read_document": read_document,
}
