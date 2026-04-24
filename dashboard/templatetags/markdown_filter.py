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

# Known root-mounted app prefixes from config/urls.py. Used to repair
# LLM-emitted markdown links that drop the leading slash (e.g.
# [x](assets/real-estate/1/) → href="assets/real-estate/1/"), which
# browsers otherwise resolve relative to the current page.
_APP_PREFIXES = (
    "assets", "stakeholders", "legal", "tasks", "cashflow", "notes",
    "healthcare", "documents", "emails", "checklists", "assistant",
    "settings",
)
_BARE_APP_HREF = re.compile(
    r'(<a\s[^>]*?\bhref=")(' + "|".join(_APP_PREFIXES) + r')/',
    re.IGNORECASE,
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
    html = _BARE_APP_HREF.sub(r'\1/\2/', html)
    return mark_safe(html)
