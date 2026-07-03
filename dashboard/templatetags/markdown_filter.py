import re

import markdown
import nh3
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# Sanitization policy: exactly the tags python-markdown emits with our
# extensions (nl2br, fenced_code, tables, sane_lists). Rendered content can
# include third-party text (assistant-quoted emails/documents, pasted notes),
# so raw HTML — script, img with event handlers, iframe, style — must not
# survive to the mark_safe sink.
_ALLOWED_TAGS = {
    "p", "br", "a", "strong", "em", "code", "pre", "ul", "ol", "li",
    "blockquote", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "hr", "del",
}
_ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "code": {"class"},  # fenced-code language, e.g. class="language-python"
    "th": {"align"},
    "td": {"align"},
}

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
    # link_rel=None: don't inject rel="noopener noreferrer" — links here are
    # overwhelmingly internal app paths and templates assert exact hrefs.
    html = nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        link_rel=None,
    )
    return mark_safe(html)
