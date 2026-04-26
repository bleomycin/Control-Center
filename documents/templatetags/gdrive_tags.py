from django import template

from documents.models import GoogleDriveSettings

register = template.Library()


@register.inclusion_tag("documents/partials/_gdrive_bulk_button.html")
def gdrive_bulk_button(entity_type, entity_pk):
    """Render a bulk Drive picker trigger button + the custom browser modal.

    Conditional on Drive being connected. Each entity detail page calls this
    inclusion tag exactly once, so the trigger and modal markup are emitted
    together — the JS module wires them on DOMContentLoaded.

    Usage:
        {% load gdrive_tags %}
        {% gdrive_bulk_button "property" property.pk %}
    """
    settings = GoogleDriveSettings.load()
    # Modal browses Drive via the backend, so api_key is no longer required —
    # but is_connected + refresh_token still are.
    connected = bool(settings.is_connected and settings.refresh_token)

    return {
        "drive_connected": connected,
        "entity_type": entity_type,
        "entity_pk": entity_pk,
    }
