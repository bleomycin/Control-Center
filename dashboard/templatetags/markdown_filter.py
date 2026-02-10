import re

import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Ensure blank line before block-level markdown elements so nl2br
# doesn't prevent the parser from recognizing them.
_BLOCK_PATTERNS = re.compile(
    r'(\S[^\n]*)\n((?=[*\-+] |\d+\. |#{1,6} |> |```|---|\*\*\*|___))',
    re.MULTILINE,
)


@register.filter
def render_markdown(value):
    """Render markdown text as HTML.

    Usage: {{ note.content|render_markdown }}
    """
    if not value:
        return ""
    text = _BLOCK_PATTERNS.sub(r'\1\n\n\2', value)
    html = markdown.markdown(
        text,
        extensions=["nl2br", "fenced_code", "tables", "sane_lists"],
    )
    return mark_safe(html)
