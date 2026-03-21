"""PDF export helper for checklists."""

from .models import Checklist


def append_checklist_sections(sections, entity_obj, fk_field):
    """Append checklist table sections to a PDF sections list.

    Args:
        sections: List of section dicts to append to.
        entity_obj: The parent entity instance.
        fk_field: The FK field name on Checklist (e.g., "related_stakeholder").
    """
    for cl in Checklist.objects.filter(**{fk_field: entity_obj}).prefetch_related("items"):
        items = cl.items.all()
        if items:
            heading = f"Checklist: {cl.name}"
            if cl.due_date:
                heading += f" (due {cl.due_date.strftime('%b %d, %Y')})"
            sections.append({
                "heading": heading,
                "type": "table",
                "headers": ["Item", "Status"],
                "rows": [[i.title, "Done" if i.is_completed else "Pending"] for i in items],
            })
