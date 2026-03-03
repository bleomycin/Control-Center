import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def render_markdown(value):
    """Render markdown text as HTML.

    Usage: {{ note.content|render_markdown }}
    """
    if not value:
        return ""
    html = markdown.markdown(
        value,
        extensions=["nl2br", "fenced_code", "tables", "sane_lists"],
    )
    return mark_safe(html)
