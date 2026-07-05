"""
Django-Q2 background tasks for the assistant.

Queued via ``django_q.tasks.async_task`` (ORM broker; qcluster runs alongside
gunicorn in entrypoint.sh). Q_CLUSTER timeout is 60s — orders of magnitude
above the ~1-2s Haiku title call.
"""

import logging

logger = logging.getLogger(__name__)


def generate_session_title(session_id, user_text, assistant_text):
    """Generate and save a session title in the background.

    Runs in a qcluster worker AFTER the streamed turn's ``done`` event, so
    the ~1-2s Haiku call no longer delays the end of a session's first
    exchange (Phase 6 Defect D). The client learns the new title by polling
    turn-status briefly after the stream ends (``title_pending`` SSE event).

    Never raises: a failed title leaves the session named "New Chat".
    """
    from .client import _generate_title, _get_client_and_model
    from .models import ChatSession

    try:
        session = ChatSession.objects.get(pk=session_id)
    except ChatSession.DoesNotExist:
        return
    # The user may have renamed the session (or a second exchange raced this
    # task) — never overwrite a title someone else already set.
    if session.title != "New Chat":
        return
    try:
        client, _model = _get_client_and_model()
    except Exception:
        logger.exception("Title task: no usable API client; leaving default title")
        return
    title = _generate_title(client, user_text, assistant_text)
    # Conditional UPDATE so a concurrent rename between the check above and
    # this write is never clobbered. updated_at is set explicitly (update()
    # bypasses auto_now) to match the old synchronous save() behavior the
    # session-list ordering relies on.
    from django.utils import timezone
    ChatSession.objects.filter(pk=session_id, title="New Chat").update(
        title=title, updated_at=timezone.now(),
    )
