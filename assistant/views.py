import json
import logging
from datetime import timedelta

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import client as assistant_client
from .forms import AssistantSettingsForm, ChatInputForm
from .models import AssistantSettings, AssistantTurn, ChatMessage, ChatSession

logger = logging.getLogger(__name__)

# Shown whenever a history-mutating operation is refused because a turn is
# still running (HTTP 409). The client surfaces this text directly.
BUSY_MESSAGE = (
    "The assistant is still working on this conversation — "
    "wait for it to finish, then try again."
)


def _live_running_turn(session):
    """The session's RUNNING turn if it is live (not stale), else None.

    A detached turn (client disconnected, still draining in background) is
    still writing ChatMessage rows — history-mutating views must not race it.
    Stale rows (worker process died mid-turn) don't count.
    """
    turn = session.turns.filter(state=AssistantTurn.STATE_RUNNING).first()
    if turn and not turn.is_stale:
        return turn
    return None


def chat_page(request, session_id=None):
    """Full-page chat view."""
    sessions = ChatSession.objects.all()

    if session_id:
        session = get_object_or_404(ChatSession, pk=session_id)
    elif sessions.exists():
        session = sessions.first()
    else:
        session = ChatSession.objects.create()
        return redirect("assistant:chat_session", session_id=session.pk)

    messages = session.messages.all()
    # Only show messages with visible content (tool-only messages served
    # their purpose during streaming and don't need permanent display)
    display_messages = [m for m in messages if m.content]

    form = ChatInputForm()

    pinned = ChatSession.objects.filter(is_pinned=True).order_by("sort_order", "-updated_at")
    unpinned = ChatSession.objects.filter(is_pinned=False).order_by("sort_order", "-updated_at")

    from documents.models import GoogleDriveSettings
    from email_links import gmail
    gmail_available = gmail.is_available()
    labels = gmail.get_labels() if gmail_available else []
    drive_connected = GoogleDriveSettings.load().is_connected

    return render(request, "assistant/chat.html", {
        "session": session,
        "sessions": sessions,
        "pinned_sessions": pinned,
        "unpinned_sessions": unpinned,
        "chat_messages": display_messages,
        "form": form,
        "gmail_available": gmail_available,
        "labels": labels,
        "drive_connected": drive_connected,
    })


def stream_message_view(request, session_id):
    """Stream assistant response via SSE."""
    session = get_object_or_404(ChatSession, pk=session_id)

    if request.method != "POST":
        return HttpResponse(status=405)

    user_text = request.POST.get("message", "").strip()
    if not user_text:
        return HttpResponse(status=400)

    mode = request.POST.get("mode", "fast")
    if mode not in ("fast", "think", "max"):
        mode = "fast"

    effort = request.POST.get("effort", "")
    if effort not in ("low", "medium", "high", "max"):
        effort = ""

    # Admission control: at most one running turn per session, enforced by
    # the one_running_turn_per_session DB constraint — not a check-then-create
    # (two fast POSTs both passed the old pre-check and interleaved their
    # ChatMessage writes). Creating the turn IS the check: the second create
    # hits IntegrityError and gets the busy refusal. A stale running row
    # (worker process died mid-turn) must not block forever, so it is
    # finalized as abandoned first — one conditional UPDATE, also race-free.
    stale_cutoff = timezone.now() - timedelta(
        seconds=AssistantTurn.STALE_AFTER_SECONDS
    )
    session.turns.filter(
        state=AssistantTurn.STATE_RUNNING, updated_at__lt=stale_cutoff
    ).update(state=AssistantTurn.STATE_ABANDONED, updated_at=timezone.now())
    try:
        with transaction.atomic():
            turn = AssistantTurn.objects.create(session=session)
    except IntegrityError:
        def _busy():
            yield (
                "event: error\ndata: "
                + json.dumps({
                    "message": "I'm still working on your previous message — "
                               "give it a moment, then try again.",
                })
                + "\n\n"
            )
        response = StreamingHttpResponse(_busy(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response

    response = StreamingHttpResponse(
        assistant_client.stream_message(
            session, user_text, mode=mode, effort=effort, turn=turn
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def turn_status(request, session_id):
    """JSON status of the session's latest assistant turn.

    This is what lets the chat client distinguish a severed SSE stream from a
    finished turn: after a disconnect it polls here until the detached turn
    (still running server-side, see client._with_heartbeat) lands, then
    reloads messages. Reads the DB, so it works from any gunicorn worker. A
    running turn whose worker stopped touching it (container died mid-turn)
    is reported as "stale" so the client can stop waiting.
    """
    session = get_object_or_404(ChatSession, pk=session_id)
    turn = session.turns.first()  # Meta.ordering = -created_at
    if turn is None:
        return JsonResponse({"state": "none"})
    state = turn.state
    if state == AssistantTurn.STATE_RUNNING and turn.is_stale:
        state = "stale"
    return JsonResponse({
        "state": state,
        "turn_id": turn.pk,
        "client_disconnected": turn.client_disconnected,
        "confirm_required": turn.confirm_required,
        "final_message_id": turn.final_message_id,
    })


@require_POST
def new_session(request):
    """Create a new chat session. POST-only: GET-triggered state changes are
    reachable by link prefetchers and bypass CSRF (Phase 5 Defect D)."""
    session = ChatSession.objects.create()
    return redirect("assistant:chat_session", session_id=session.pk)


@require_POST
def bulk_delete_sessions(request):
    """Delete multiple chat sessions at once."""
    ids = request.POST.getlist("selected")
    # Same race as delete_session: a session with a live running turn is
    # still being written by a detached worker — refuse the whole batch.
    for busy_session in ChatSession.objects.filter(pk__in=ids):
        if _live_running_turn(busy_session):
            return HttpResponse(BUSY_MESSAGE, status=409)
    if ids:
        # Don't delete the current session if it's in the list
        current_id = request.POST.get("current")
        ChatSession.objects.filter(pk__in=ids).exclude(pk=current_id).delete()
        # Also delete current if selected (handle redirect)
        if current_id in ids:
            ChatSession.objects.filter(pk=current_id).delete()

    if request.headers.get("HX-Request"):
        remaining = ChatSession.objects.first()
        if remaining:
            response = HttpResponse(status=200)
            response["HX-Redirect"] = remaining.get_absolute_url()
        else:
            response = HttpResponse(status=200)
            response["HX-Redirect"] = "/assistant/"
        return response
    return redirect("assistant:chat")


@require_POST
def delete_session(request, session_id):
    """Delete a chat session."""
    session = get_object_or_404(ChatSession, pk=session_id)
    # Deleting cascades to the running turn's ChatMessages while a detached
    # worker may still be writing them — refuse until the turn finishes.
    if _live_running_turn(session):
        return HttpResponse(BUSY_MESSAGE, status=409)
    session.delete()

    if request.headers.get("HX-Request"):
        remaining = ChatSession.objects.first()
        if remaining:
            response = HttpResponse(status=200)
            response["HX-Redirect"] = remaining.get_absolute_url()
            return response
        else:
            response = HttpResponse(status=200)
            response["HX-Redirect"] = "/assistant/"
            return response

    return redirect("assistant:chat")


@require_POST
def rename_session(request, session_id):
    """Rename a chat session title."""
    session = get_object_or_404(ChatSession, pk=session_id)
    new_title = request.POST.get("title", "").strip()
    if new_title:
        session.title = new_title
        session.save(update_fields=["title"])

    if request.headers.get("HX-Request"):
        pinned = ChatSession.objects.filter(is_pinned=True).order_by("sort_order", "-updated_at")
        unpinned = ChatSession.objects.filter(is_pinned=False).order_by("sort_order", "-updated_at")
        return render(request, "assistant/partials/_session_list.html", {
            "pinned_sessions": pinned,
            "unpinned_sessions": unpinned,
            "session": session,
        })
    return redirect("assistant:chat_session", session_id=session.pk)


@require_POST
def retry_message(request, session_id, message_id):
    """Retry from an assistant message: delete its turn and everything after,
    return the preceding user text."""
    session = get_object_or_404(ChatSession, pk=session_id)
    msg = get_object_or_404(ChatMessage, pk=message_id, session=session)

    if msg.role != "assistant":
        return JsonResponse({"error": "Can only retry assistant messages"}, status=400)

    # A detached running turn may still be writing this history (Defect C).
    if _live_running_turn(session):
        return JsonResponse({"error": BUSY_MESSAGE}, status=409)

    # Find the REAL user message that started this turn. Tool-result rows are
    # also role="user" with content="" — matching one of those returned empty
    # text and made Retry silently destructive (deleted the answer, re-asked
    # nothing).
    user_msg = (
        session.messages.filter(
            role="user", tool_data__isnull=True, created_at__lt=msg.created_at
        )
        .exclude(content="")
        .order_by("-created_at")
        .first()
    )
    user_text = user_msg.content if user_msg else ""

    # Delete the whole turn being retried: everything after the user message
    # that started it (its tool pairs included), so the resend regenerates
    # from a clean boundary.
    if user_msg is not None:
        session.messages.filter(created_at__gt=user_msg.created_at).delete()
    else:
        session.messages.filter(created_at__gte=msg.created_at).delete()

    return JsonResponse({"user_text": user_text, "action": "retry"})


@require_POST
def edit_message(request, session_id, message_id):
    """Edit a user message: delete it and everything after, return its text."""
    session = get_object_or_404(ChatSession, pk=session_id)
    msg = get_object_or_404(ChatMessage, pk=message_id, session=session)

    if msg.role != "user":
        return JsonResponse({"error": "Can only edit user messages"}, status=400)

    # A detached running turn may still be writing this history (Defect C).
    if _live_running_turn(session):
        return JsonResponse({"error": BUSY_MESSAGE}, status=409)

    user_text = msg.content

    # Delete this message and everything after it
    session.messages.filter(created_at__gte=msg.created_at).delete()

    return JsonResponse({"user_text": user_text, "action": "edit"})


@require_POST
def prune_history(request, session_id):
    """Delete older messages, keeping roughly the last N.

    The cut never lands mid tool-pair: it advances to the next real user
    message (role=user, no tool_data, non-empty content), the same clean turn
    boundary the truncation anchor uses. A blind "keep last N" slice could
    strand a tool_result whose tool_use was deleted — a permanent DB orphan
    that the pairing repair then re-trims on every request.
    """
    session = get_object_or_404(ChatSession, pk=session_id)
    # A detached running turn may still be appending to this history.
    if _live_running_turn(session):
        return HttpResponse(BUSY_MESSAGE, status=409)

    try:
        keep = int(request.POST.get("keep", 20))
    except (TypeError, ValueError):
        keep = 20
    keep = max(2, min(keep, 500))

    msgs = list(session.messages.order_by("created_at", "pk"))
    if len(msgs) > keep:
        cut = len(msgs) - keep
        while cut < len(msgs) and not (
            msgs[cut].role == "user"
            and not msgs[cut].tool_data
            and (msgs[cut].content or "").strip()
        ):
            cut += 1
        # No clean boundary in the tail (pathological history) → prune
        # nothing rather than create orphans.
        if cut < len(msgs):
            ChatMessage.objects.filter(
                pk__in=[m.pk for m in msgs[:cut]]
            ).delete()

    messages = session.messages.all()
    display_messages = [m for m in messages if m.content]

    return render(request, "assistant/partials/_message_list.html", {
        "chat_messages": display_messages,
    })


def session_list(request):
    """Return the session list partial (for HTMX refresh)."""
    current_id = request.GET.get("current")
    session = None
    if current_id:
        try:
            session = ChatSession.objects.get(pk=current_id)
        except ChatSession.DoesNotExist:
            pass
    pinned = ChatSession.objects.filter(is_pinned=True).order_by("sort_order", "-updated_at")
    unpinned = ChatSession.objects.filter(is_pinned=False).order_by("sort_order", "-updated_at")
    return render(request, "assistant/partials/_session_list.html", {
        "pinned_sessions": pinned,
        "unpinned_sessions": unpinned,
        "session": session,
    })


@require_POST
def toggle_pin(request, session_id):
    """Toggle pin status of a chat session."""
    s = get_object_or_404(ChatSession, pk=session_id)
    s.is_pinned = not s.is_pinned
    if s.is_pinned:
        # Place at the end of pinned list
        max_order = ChatSession.objects.filter(is_pinned=True).exclude(pk=s.pk).count()
        s.sort_order = max_order
    else:
        s.sort_order = 0
    s.save(update_fields=["is_pinned", "sort_order"])

    if request.headers.get("HX-Request"):
        pinned = ChatSession.objects.filter(is_pinned=True).order_by("sort_order", "-updated_at")
        unpinned = ChatSession.objects.filter(is_pinned=False).order_by("sort_order", "-updated_at")
        current_id = request.POST.get("current")
        current = None
        if current_id:
            try:
                current = ChatSession.objects.get(pk=current_id)
            except ChatSession.DoesNotExist:
                pass
        return render(request, "assistant/partials/_session_list.html", {
            "pinned_sessions": pinned,
            "unpinned_sessions": unpinned,
            "session": current,
        })
    return JsonResponse({"pinned": s.is_pinned})


@require_POST
def reorder_sessions(request):
    """Reorder sessions via drag-and-drop. Expects JSON body with ordered IDs."""
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    pinned_ids = data.get("pinned", [])
    for i, pk in enumerate(pinned_ids):
        ChatSession.objects.filter(pk=pk).update(sort_order=i, is_pinned=True)

    unpinned_ids = data.get("unpinned", [])
    for i, pk in enumerate(unpinned_ids):
        ChatSession.objects.filter(pk=pk).update(is_pinned=False, sort_order=i)

    return JsonResponse({"ok": True})


def process_email_form(request):
    """Return the Process Email modal form."""
    from email_links import gmail
    from documents import gdrive
    gmail_available = gmail.is_available()
    labels = gmail.get_labels() if gmail_available else []
    drive_connected = gdrive.is_connected()
    drive_settings = None
    if drive_connected:
        drive_settings = gdrive._get_settings()
    return render(request, "assistant/partials/_process_email_form.html", {
        "gmail_available": gmail_available,
        "labels": labels,
        "drive_connected": drive_connected,
        "drive_settings": drive_settings,
    })


def gmail_thread_search(request):
    """HTMX endpoint: search Gmail threads for the assistant email picker."""
    from email_links import gmail
    if not gmail.is_available():
        return render(request, "assistant/partials/_gmail_thread_results.html", {
            "error": "Gmail is not connected.",
        })
    query = request.GET.get("q", "")
    page_token = request.GET.get("page_token", "")
    label = request.GET.get("label", "")
    label_ids = [label] if label else None
    try:
        data = gmail.search_threads(
            query=query,
            max_results=15,
            page_token=page_token or None,
            label_ids=label_ids,
        )
    except Exception as e:
        logger.exception("Gmail search failed")
        return render(request, "assistant/partials/_gmail_thread_results.html", {
            "error": f"Gmail search error: {e}",
        })
    mode = request.GET.get("mode", "")
    callback = "attachGmailThread" if mode == "attach" else ""
    callback_label = "Add" if mode == "attach" else ""
    return render(request, "assistant/partials/_gmail_thread_results.html", {
        "results": data.get("threads"),
        "next_page_token": data.get("next_page_token"),
        "query": query,
        "label": label,
        "browsing": not query,
        "mode": mode,
        "callback": callback,
        "callback_label": callback_label,
    })


import difflib
import re

# Known boilerplate blocks to strip entirely from email bodies.
# These are specific recurring disclaimers that waste tokens and
# contain no useful contact or entity information.
_BOILERPLATE_PATTERNS = [
    # Armanino confidentiality + entity structure disclaimer
    re.compile(
        r"CONFIDENTIALITY AND PRIVACY NOTICE.*?subsidiary entities provide tax, advisory, and business consulting services\."
        r".*?not licensed CPA firms\.",
        re.DOTALL,
    ),
]


def _strip_boilerplate(body):
    """Remove known boilerplate blocks from email bodies."""
    if not body:
        return body
    for pattern in _BOILERPLATE_PATTERNS:
        body = pattern.sub("", body)
    return body.rstrip()


# Subject prefixes that indicate a forwarded email. For these we never dedupe:
# the user attached the forward on purpose, so the whole thing is shown.
_FORWARD_SUBJECT_RE = re.compile(r"^\s*(fw|fwd)\s*:", re.IGNORECASE)

# Placeholder left in the body where a redundant quoted block is removed, so
# the removal is never silent — the model and user can see content was cut and
# that the originals are rendered as separate messages above.
_OMITTED_QUOTE_NOTE = "[Earlier quoted messages in this thread omitted — see the messages above.]"

# A contiguous run of lines that also appears verbatim in an earlier message
# is treated as a quoted copy and dropped only if it carries at least this many
# non-whitespace characters. Smaller incidental matches (greetings, blank
# lines, a shared phrase) are kept so the text is never fragmented.
_MIN_QUOTE_CHARS = 40


def _is_forward_subject(subject):
    """True if the subject indicates a forwarded email (FW:/Fwd:)."""
    return bool(_FORWARD_SUBJECT_RE.match(subject or ""))


def _normalize_line(line):
    """Normalize one line for quote matching: drop leading ">"/"|" quote
    markers (including nested "> >"), lowercase, and collapse internal
    whitespace, so re-wrapped / re-quoted copies of a line compare equal."""
    line = re.sub(r"^(\s*[>|]\s?)+", "", line)
    return re.sub(r"\s+", " ", line).strip().lower()


def _dedupe_against_earlier(body, earlier_bodies):
    """Remove quoted copies of earlier thread messages from `body`.

    This is the durable de-duplication core. Instead of guessing where a
    "quote" begins from client-specific markers, it diffs `body` line-by-line
    (difflib) against the concatenation of the earlier messages we already
    render separately, and drops only the contiguous runs that match that
    earlier content. Everything novel to this message is preserved — including
    replies interleaved *between* quoted passages (top-posted, bottom-posted,
    and inline replies all work). Unique forwarded content matches nothing and
    is kept in full. Each removed run leaves a single visible note.

    Returns the cleaned body (CRLF normalized to LF).
    """
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    orig_lines = body.split("\n")
    norm_lines = [_normalize_line(ln) for ln in orig_lines]

    ref = []
    for earlier in earlier_bodies:
        earlier = (earlier or "").replace("\r\n", "\n").replace("\r", "\n")
        ref.extend(_normalize_line(ln) for ln in earlier.split("\n"))
    if not any(ref):
        return body

    matcher = difflib.SequenceMatcher(None, ref, norm_lines, autojunk=False)
    out = []
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            quoted_chars = sum(len(norm_lines[j]) for j in range(j1, j2))
            if quoted_chars >= _MIN_QUOTE_CHARS:
                # A substantial verbatim copy of earlier content — drop it,
                # but mark the gap so the removal is visible (and coalesce
                # adjacent notes).
                if not (out and out[-1] == _OMITTED_QUOTE_NOTE):
                    out.append(_OMITTED_QUOTE_NOTE)
                continue
        out.extend(orig_lines[j1:j2])

    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)  # tidy gaps left by removals
    return cleaned.strip()


def _clean_email_body(body, *, is_first, is_forward, earlier_bodies):
    """Clean a single thread message body for inclusion in the thread text.

    Always removes known boilerplate disclaimers. De-duplicates quoted copies
    of earlier thread messages via a line-level diff against those messages
    (see _dedupe_against_earlier), so nothing unique is ever dropped: the first
    message (`is_first`), forwarded subjects (`is_forward`), and any text that
    doesn't match a sibling are all preserved. Removed runs leave a visible
    note, so de-duplication is never silent.
    """
    body = (body or "").strip()
    if not is_first and not is_forward and earlier_bodies:
        body = _dedupe_against_earlier(body, earlier_bodies)
    return _strip_boilerplate(body)


def gmail_thread_fetch(request):
    """JSON endpoint: fetch a Gmail thread's messages as formatted text."""
    from email_links import gmail
    thread_id = request.GET.get("thread_id", "")
    if not thread_id:
        return JsonResponse({"error": "No thread_id provided"}, status=400)
    try:
        thread_messages = gmail.get_thread_messages(thread_id)
    except Exception as e:
        logger.exception("Gmail thread fetch failed")
        return JsonResponse({"error": str(e)}, status=500)
    if not thread_messages:
        return JsonResponse({"error": "No messages found in thread"}, status=404)
    # Format messages into structured text. Quoted reply blocks are stripped
    # only when redundant (a reply chain whose quotes duplicate earlier
    # messages); forwarded content is preserved (see _clean_email_body).
    parts = []
    subject = request.GET.get("subject", "Email Thread")
    is_forward = _is_forward_subject(subject)
    parts.append(f"Subject: {subject}")
    parts.append(f"Thread: {len(thread_messages)} message(s)\n")
    for i, msg in enumerate(thread_messages, 1):
        parts.append(f"--- Message {i} ---")
        parts.append(f"From: {msg.get('from_name', '')} <{msg.get('from_email', '')}>")
        parts.append(f"Date: {msg.get('date', '')}")
        earlier_bodies = [m.get("body", "") for m in thread_messages[: i - 1]]
        body = _clean_email_body(
            msg.get("body", ""), is_first=(i == 1), is_forward=is_forward,
            earlier_bodies=earlier_bodies,
        )
        parts.append(body)
        parts.append("")
    return JsonResponse({"formatted_text": "\n".join(parts), "subject": subject})


@require_POST
def drawer_session(request):
    """Return or create a session for the drawer.

    ?new=1 forces a fresh session.  Otherwise returns the most recent.
    POST-only even though the common case is a read: both branches can create
    a session, and GET state changes are prefetchable and bypass CSRF
    (Defect D). The endpoint is only ever called from JS (base.html), which
    already sends the CSRF header.
    """
    if request.GET.get("new"):
        session = ChatSession.objects.create()
    else:
        session = ChatSession.objects.first()
        if not session:
            session = ChatSession.objects.create()
    return JsonResponse({"session_id": session.pk, "title": session.title})


def drawer_messages(request, session_id):
    """Return rendered messages for the drawer."""
    session = get_object_or_404(ChatSession, pk=session_id)
    all_msgs = session.messages.all()
    display_messages = [m for m in all_msgs if m.content]
    return render(request, "assistant/partials/_message_list.html", {
        "chat_messages": display_messages,
    })


@require_POST
def warm_cache(request):
    """Fire a minimal API call to warm Anthropic's prompt cache.

    The tools array MUST match what real requests send (_get_active_tools,
    not raw TOOL_DEFINITIONS): tools are position 0 of the cache key, so a
    warm with the wrong array writes an entry no real request can read —
    every drawer-open paid a full 2x (1h TTL) cache write for nothing.
    max_tokens=0 is the supported pre-warm form: prefill runs (writing the
    cache at the system breakpoint, whose entry covers the tools+system
    prefix as one unit) and returns immediately with no output tokens
    billed.
    """
    try:
        from .client import (
            _build_system_prompt,
            _get_active_tools,
            _get_client_and_model,
        )
        client, model_name = _get_client_and_model()
        client.messages.create(
            model=model_name,
            max_tokens=0,
            system=_build_system_prompt(),
            tools=_get_active_tools([]),
            messages=[{"role": "user", "content": "hi"}],
        )
    except Exception:
        pass
    return JsonResponse({"ok": True})


def assistant_settings(request):
    """Configure AI assistant API key and model."""
    instance = AssistantSettings.load()
    if request.method == "POST":
        form = AssistantSettingsForm(request.POST, instance=instance)
        if form.is_valid():
            form.save()
            messages.success(request, "Assistant settings saved.")
            return redirect("assistant:settings")
    else:
        form = AssistantSettingsForm(instance=instance)
    return render(request, "assistant/settings.html", {
        "form": form,
        "settings_obj": instance,
    })
