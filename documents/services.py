"""
Pure-Python services for the documents app.

Service functions return plain dicts (no HttpResponse / Django request objects)
so they can be called from views, the assistant tool layer, management commands,
and tests without an HTTP round-trip.
"""

from django.apps import apps
from django.db import transaction

from .models import Document


# Same mapping the documents views use. Kept here as the canonical source so
# both the bulk-link view and the assistant tool resolve entity types identically.
ENTITY_CONFIG = {
    "realestate": ("assets.RealEstate", "related_property"),
    "investment": ("assets.Investment", "related_investment"),
    "loan": ("assets.Loan", "related_loan"),
    "lease": ("assets.Lease", "related_lease"),
    "policy": ("assets.InsurancePolicy", "related_policy"),
    "vehicle": ("assets.Vehicle", "related_vehicle"),
    "aircraft": ("assets.Aircraft", "related_aircraft"),
    "stakeholder": ("stakeholders.Stakeholder", "related_stakeholder"),
    "legalmatter": ("legal.LegalMatter", "related_legal_matter"),
    # Legacy aliases used by the existing view URL routes — keep accepting them
    # so the existing endpoint contract stays intact.
    "property": ("assets.RealEstate", "related_property"),
    "legal_matter": ("legal.LegalMatter", "related_legal_matter"),
}


def _resolve_entity(entity_type, entity_id):
    """Return (entity, fk_field) or raise LookupError / ValueError on failure."""
    if entity_type not in ENTITY_CONFIG:
        raise ValueError(f"Unknown entity_type: {entity_type}")
    app_model, fk_field = ENTITY_CONFIG[entity_type]
    Model = apps.get_model(app_model)
    try:
        entity = Model.objects.get(pk=entity_id)
    except Model.DoesNotExist as exc:
        raise LookupError(
            f"{Model.__name__} with id={entity_id} not found"
        ) from exc
    return entity, fk_field


def _normalize_file(f):
    """Normalize a single picker-file dict to the trimmed shape used downstream.

    Returns None if the dict is unusable (no id), else a dict with the
    same keys plus a derived `title` and `gdrive_url` fallback.
    """
    if not isinstance(f, dict):
        return None
    file_id = (f.get("id") or "").strip()
    if not file_id:
        return None
    name = (f.get("name") or "").strip()
    title = name.rsplit(".", 1)[0] if "." in name else name
    url = (f.get("url") or "").strip()
    if not url:
        url = f"https://drive.google.com/file/d/{file_id}/view"
    mime = (f.get("mimeType") or "").strip()
    return {
        "id": file_id,
        "name": name,
        "mimeType": mime,
        "url": url,
        "title": title or "Untitled",
    }


def bulk_link_drive_files(entity_type, entity_id, files, dry_run=False):
    """Create Document records for each Drive file and link them to the target entity.

    Args:
      entity_type: one of 'realestate','investment','loan','lease','policy',
                   'vehicle','aircraft','stakeholder','legalmatter'
                   (legacy aliases 'property' and 'legal_matter' are also accepted)
      entity_id:   pk of the target entity
      files:       list of {id, name, mimeType, url} dicts (from the picker /
                   [AttachedDriveFiles] marker)
      dry_run:     if True, return preview only (no DB writes)

    Returns dict:
      dry_run=True  -> {"dry_run": True, "target": {...}, "would_create": [...],
                        "summary": "..."}
      dry_run=False -> {"dry_run": False, "target": {...}, "linked": [...],
                        "summary": "..."}
      error case    -> {"error": "..."}
    """
    # Validate entity_type early (cheap; no DB hit)
    if entity_type not in ENTITY_CONFIG:
        return {
            "error": (
                f"Unknown entity_type: {entity_type!r}. Valid values: "
                f"realestate, investment, loan, lease, policy, vehicle, "
                f"aircraft, stakeholder, legalmatter"
            )
        }

    # Validate files list shape
    if not isinstance(files, list):
        return {"error": "files must be a list"}
    if not files:
        return {"error": "files list is empty"}

    # Normalize and drop unusable entries (missing id)
    normalized = []
    for f in files:
        n = _normalize_file(f)
        if n is not None:
            normalized.append(n)
    if not normalized:
        return {"error": "no valid files in the list (each file must have an id)"}

    # Resolve target entity
    try:
        entity, fk_field = _resolve_entity(entity_type, entity_id)
    except ValueError as exc:
        return {"error": str(exc)}
    except LookupError as exc:
        return {"error": str(exc)}

    target = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "name": str(entity),
    }

    # Snapshot the gdrive_file_ids already linked to this entity so we can
    # report new vs. reused per-file (matches existing endpoint dedupe behavior).
    existing_ids = set(
        Document.objects
        .filter(**{fk_field: entity})
        .exclude(gdrive_file_id="")
        .values_list("gdrive_file_id", flat=True)
    )

    if dry_run:
        would_create = []
        new_count = 0
        reuse_count = 0
        for f in normalized:
            reuses = f["id"] in existing_ids
            if reuses:
                reuse_count += 1
            else:
                new_count += 1
            would_create.append({
                "id": f["id"],
                "name": f["name"],
                "title": f["title"],
                "mimeType": f["mimeType"],
                "url": f["url"],
                "action": "reuse" if reuses else "create",
            })
        return {
            "dry_run": True,
            "target": target,
            "would_create": would_create,
            "summary": (
                f"Would link {len(normalized)} file(s) to "
                f"{target['name']} ({entity_type} #{entity_id}): "
                f"{new_count} new, {reuse_count} already exists"
            ),
        }

    # Execute: create + link inside a single transaction so a failure mid-loop
    # rolls back any partial state.
    linked = []
    new_count = 0
    reuse_count = 0
    with transaction.atomic():
        for f in normalized:
            if f["id"] in existing_ids:
                # Already linked to this entity by gdrive_file_id — reuse the
                # existing Document rather than creating a duplicate.
                doc = (
                    Document.objects
                    .filter(**{fk_field: entity}, gdrive_file_id=f["id"])
                    .first()
                )
                if doc is not None:
                    linked.append({
                        "document_id": doc.pk,
                        "id": f["id"],
                        "name": f["name"],
                        "title": doc.title,
                        "created": False,
                    })
                    reuse_count += 1
                    continue
                # Fall through to create if for some reason the row vanished.

            doc = Document.objects.create(
                title=f["title"],
                gdrive_file_id=f["id"],
                gdrive_url=f["url"],
                gdrive_file_name=f["name"],
                gdrive_mime_type=f["mimeType"],
                **{fk_field: entity},
            )
            existing_ids.add(f["id"])
            linked.append({
                "document_id": doc.pk,
                "id": f["id"],
                "name": f["name"],
                "title": doc.title,
                "created": True,
            })
            new_count += 1

    return {
        "dry_run": False,
        "target": target,
        "linked": linked,
        "summary": (
            f"Linked {len(linked)} file(s) to {target['name']} "
            f"({entity_type} #{entity_id}): "
            f"{new_count} new, {reuse_count} reused"
        ),
    }
