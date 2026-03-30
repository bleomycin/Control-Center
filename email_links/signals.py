"""
Clean up orphaned EmailLinks when an entity is deleted.

Django's on_delete=SET_NULL uses a bulk UPDATE that bypasses model save(),
so we catch it with pre_delete (capture linked IDs) + post_delete (delete
any that are now fully orphaned).
"""

from django.db.models.signals import pre_delete, post_delete
from django.dispatch import receiver

from .views import ENTITY_CONFIG, FK_ID_FIELDS


def _get_orphan_filter():
    """Return kwargs that match EmailLinks with ALL FK fields null."""
    return {f"{fk_id}__isnull": True for fk_id in FK_ID_FIELDS}


def _on_pre_delete(sender, instance, **kwargs):
    """Stash the IDs of EmailLinks about to lose a FK via SET_NULL."""
    if hasattr(instance, "email_links"):
        ids = list(instance.email_links.values_list("pk", flat=True))
        if ids:
            instance._orphan_candidate_email_ids = ids


def _on_post_delete(sender, instance, **kwargs):
    """Delete any of the stashed EmailLinks that are now fully orphaned."""
    ids = getattr(instance, "_orphan_candidate_email_ids", None)
    if not ids:
        return
    from .models import EmailLink
    EmailLink.objects.filter(pk__in=ids, **_get_orphan_filter()).delete()


def connect_signals():
    """Register pre/post_delete on every entity model that can link to emails."""
    from django.apps import apps

    for app_model, _ in ENTITY_CONFIG.values():
        Model = apps.get_model(app_model)
        pre_delete.connect(_on_pre_delete, sender=Model, weak=False)
        post_delete.connect(_on_post_delete, sender=Model, weak=False)
