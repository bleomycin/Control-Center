from django import template

from dashboard.choices import get_choice_label

register = template.Library()


@register.filter
def choice_label(value, category):
    """Return the display label for a choice value.

    Usage: {{ stakeholder.entity_type|choice_label:"entity_type" }}
    """
    return get_choice_label(category, value)
