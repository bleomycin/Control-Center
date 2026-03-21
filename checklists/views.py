from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ChecklistForm, ChecklistItemForm
from .models import Checklist, ChecklistItem

# Maps URL slug → model FK field name
FK_FIELD_MAP = {
    "stakeholder": "related_stakeholder",
    "task": "related_task",
    "note": "related_note",
    "property": "related_property",
    "legal_matter": "related_legal_matter",
}

# Maps URL slug → (app_label.ModelName, import path)
ENTITY_MODEL_MAP = {
    "stakeholder": ("stakeholders", "Stakeholder"),
    "task": ("tasks", "Task"),
    "note": ("notes", "Note"),
    "property": ("assets", "RealEstate"),
    "legal_matter": ("legal", "LegalMatter"),
}


def _get_entity(entity_type, entity_pk):
    """Look up the parent entity by type slug and PK."""
    if entity_type not in ENTITY_MODEL_MAP:
        from django.http import Http404
        raise Http404(f"Unknown entity type: {entity_type}")
    app_label, model_name = ENTITY_MODEL_MAP[entity_type]
    from django.apps import apps
    model = apps.get_model(app_label, model_name)
    return get_object_or_404(model, pk=entity_pk)


def _entity_from_checklist(checklist):
    """Determine the entity type slug and object from a checklist's FK fields."""
    for slug, fk_field in FK_FIELD_MAP.items():
        obj = getattr(checklist, fk_field, None)
        if obj is not None:
            return slug, obj
    return None, None


def get_checklists_context(entity_obj, entity_type):
    """Build template context for all checklists on an entity.

    Called by consuming detail views to merge into their context.
    """
    fk_field = FK_FIELD_MAP[entity_type]
    checklists = (
        Checklist.objects.filter(**{fk_field: entity_obj})
        .prefetch_related("items")
    )
    checklists_data = []
    for cl in checklists:
        items = cl.items.all()
        checklists_data.append({
            "checklist": cl,
            "items": items,
            "item_count": len(items),
            "done_count": sum(1 for i in items if i.is_completed),
            "item_form": ChecklistItemForm(),
        })
    return {
        "checklists_data": checklists_data,
        "checklist_form": ChecklistForm(),
        "entity_type": entity_type,
        "entity_obj": entity_obj,
    }


def _section_context(checklist):
    """Return full section context from a checklist (for HTMX re-render)."""
    entity_type, entity_obj = _entity_from_checklist(checklist)
    if entity_obj is None:
        return {"checklists_data": [], "checklist_form": ChecklistForm(),
                "entity_type": "", "entity_obj": None}
    return get_checklists_context(entity_obj, entity_type)


SECTION_TEMPLATE = "checklists/partials/_checklists_section.html"
ITEMS_TEMPLATE = "checklists/partials/_checklist_items.html"
ITEM_EDIT_TEMPLATE = "checklists/partials/_checklist_item_edit.html"


# ---------------------------------------------------------------------------
# Checklist-level views
# ---------------------------------------------------------------------------

def checklist_add(request, entity_type, entity_pk):
    """Create a new named checklist on an entity."""
    entity_obj = _get_entity(entity_type, entity_pk)
    if request.method == "POST":
        form = ChecklistForm(request.POST)
        if form.is_valid():
            cl = form.save(commit=False)
            fk_field = FK_FIELD_MAP[entity_type]
            setattr(cl, fk_field, entity_obj)
            cl.sort_order = Checklist.objects.filter(**{fk_field: entity_obj}).count()
            cl.save()
    return render(request, SECTION_TEMPLATE, get_checklists_context(entity_obj, entity_type))


@require_POST
def checklist_delete(request, pk):
    """Delete an entire checklist and all its items."""
    cl = get_object_or_404(Checklist, pk=pk)
    ctx = _section_context(cl)
    cl.delete()
    # Re-fetch context after deletion
    if ctx["entity_obj"]:
        ctx = get_checklists_context(ctx["entity_obj"], ctx["entity_type"])
    return render(request, SECTION_TEMPLATE, ctx)


# ---------------------------------------------------------------------------
# Item-level views
# ---------------------------------------------------------------------------

def item_add(request, checklist_pk):
    """Add a new item to a checklist."""
    cl = get_object_or_404(Checklist, pk=checklist_pk)
    if request.method == "POST":
        form = ChecklistItemForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.checklist = cl
            item.sort_order = cl.items.count()
            item.save()
    return render(request, SECTION_TEMPLATE, _section_context(cl))


@require_POST
def item_toggle(request, pk):
    """Toggle an item's completion status."""
    item = get_object_or_404(ChecklistItem, pk=pk)
    item.is_completed = not item.is_completed
    item.completed_at = timezone.now() if item.is_completed else None
    item.save()
    return render(request, SECTION_TEMPLATE, _section_context(item.checklist))


def item_edit(request, pk):
    """Inline edit an item title. GET shows form, POST saves."""
    item = get_object_or_404(ChecklistItem, pk=pk)
    cl = item.checklist
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        if title:
            item.title = title
            item.save()
        return render(request, SECTION_TEMPLATE, _section_context(cl))
    if request.GET.get("cancel"):
        return render(request, SECTION_TEMPLATE, _section_context(cl))
    return render(request, ITEM_EDIT_TEMPLATE, {"item": item})


@require_POST
def item_delete(request, pk):
    """Delete a checklist item."""
    item = get_object_or_404(ChecklistItem, pk=pk)
    cl = item.checklist
    item.delete()
    return render(request, SECTION_TEMPLATE, _section_context(cl))
