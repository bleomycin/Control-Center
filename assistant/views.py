import json
import logging

from django.contrib import messages
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import client as assistant_client
from .forms import AssistantSettingsForm, ChatInputForm
from .models import AssistantSettings, ChatMessage, ChatSession

logger = logging.getLogger(__name__)


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

    return render(request, "assistant/chat.html", {
        "session": session,
        "sessions": sessions,
        "pinned_sessions": pinned,
        "unpinned_sessions": unpinned,
        "chat_messages": display_messages,
        "form": form,
    })


def send_message_view(request, session_id):
    """Handle a user message via HTMX POST."""
    session = get_object_or_404(ChatSession, pk=session_id)

    if request.method != "POST":
        return HttpResponse(status=405)

    user_text = request.POST.get("message", "").strip()
    if not user_text:
        return HttpResponse(status=400)

    new_messages = assistant_client.send_message(session, user_text)

    display_messages = [m for m in new_messages if m.content]

    response = render(request, "assistant/partials/_message_list.html", {
        "chat_messages": display_messages,
    })
    # Trigger session list refresh (title may have changed)
    response["HX-Trigger"] = "refreshSessions"
    return response


def stream_message_view(request, session_id):
    """Stream assistant response via SSE."""
    session = get_object_or_404(ChatSession, pk=session_id)

    if request.method != "POST":
        return HttpResponse(status=405)

    user_text = request.POST.get("message", "").strip()
    if not user_text:
        return HttpResponse(status=400)

    response = StreamingHttpResponse(
        assistant_client.stream_message(session, user_text),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def new_session(request):
    """Create a new chat session."""
    session = ChatSession.objects.create()
    if request.headers.get("HX-Request"):
        return redirect("assistant:chat_session", session_id=session.pk)
    return redirect("assistant:chat_session", session_id=session.pk)


@require_POST
def bulk_delete_sessions(request):
    """Delete multiple chat sessions at once."""
    ids = request.POST.getlist("selected")
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


def delete_session(request, session_id):
    """Delete a chat session."""
    session = get_object_or_404(ChatSession, pk=session_id)
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


def retry_message(request, session_id, message_id):
    """Retry from an assistant message: delete it and everything after, return preceding user text."""
    if request.method != "POST":
        return HttpResponse(status=405)

    session = get_object_or_404(ChatSession, pk=session_id)
    msg = get_object_or_404(ChatMessage, pk=message_id, session=session)

    if msg.role != "assistant":
        return JsonResponse({"error": "Can only retry assistant messages"}, status=400)

    # Find the user message immediately before this assistant message
    user_msg = (
        session.messages.filter(role="user", created_at__lt=msg.created_at)
        .order_by("-created_at")
        .first()
    )
    user_text = user_msg.content if user_msg else ""

    # Delete this message and everything after it
    session.messages.filter(created_at__gte=msg.created_at).delete()

    return JsonResponse({"user_text": user_text, "action": "retry"})


def edit_message(request, session_id, message_id):
    """Edit a user message: delete it and everything after, return its text."""
    if request.method != "POST":
        return HttpResponse(status=405)

    session = get_object_or_404(ChatSession, pk=session_id)
    msg = get_object_or_404(ChatMessage, pk=message_id, session=session)

    if msg.role != "user":
        return JsonResponse({"error": "Can only edit user messages"}, status=400)

    user_text = msg.content

    # Delete this message and everything after it
    session.messages.filter(created_at__gte=msg.created_at).delete()

    return JsonResponse({"user_text": user_text, "action": "edit"})


def prune_history(request, session_id):
    """Delete older messages, keeping the last N."""
    session = get_object_or_404(ChatSession, pk=session_id)
    keep = int(request.POST.get("keep", 20))

    message_ids = list(
        session.messages.order_by("-created_at").values_list("pk", flat=True)[keep:]
    )
    ChatMessage.objects.filter(pk__in=message_ids).delete()

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
    return render(request, "assistant/partials/_gmail_thread_results.html", {
        "results": data.get("threads"),
        "next_page_token": data.get("next_page_token"),
        "query": query,
        "label": label,
        "browsing": not query,
    })


import re

# Patterns that mark the start of a trailing quoted reply block.
# Everything from this line onward is a copy of previous messages.
_REPLY_MARKERS = [
    # Gmail: "On Fri, Mar 20, 2026 at 11:11 AM Name <email> wrote:"
    # The "wrote:" may be on the next line due to line wrapping
    re.compile(r"^On .+\d{4}.+wrote:\s*$", re.MULTILINE),
    re.compile(r"^On .+\d{4}.+>\s*\nwrote:", re.MULTILINE),
    # Outlook: "From: Name\nSent: Date" reply header block
    re.compile(r"^From: .+\nSent: ", re.MULTILINE),
    # Divider lines (5+ underscores or dashes) used by some clients
    re.compile(r"^_{5,}$|^-{5,}$", re.MULTILINE),
]

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


def _strip_quoted_reply(body):
    """Remove the trailing quoted reply block from an email body.

    Finds the first reply marker (e.g., "On ... wrote:" or "From: ...")
    and truncates everything after it. Preserves inline content above
    the marker, including inline replies.
    """
    if not body:
        return body
    # Find the earliest reply marker position
    earliest = len(body)
    for pattern in _REPLY_MARKERS:
        match = pattern.search(body)
        if match and match.start() < earliest:
            earliest = match.start()
    if earliest < len(body):
        stripped = body[:earliest].rstrip()
        # Don't return empty — if the entire body was a quote, keep it
        if stripped:
            return stripped
    return body


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
    # Format messages into structured text, stripping trailing quoted blocks
    parts = []
    subject = request.GET.get("subject", "Email Thread")
    parts.append(f"Subject: {subject}")
    parts.append(f"Thread: {len(thread_messages)} message(s)\n")
    for i, msg in enumerate(thread_messages, 1):
        parts.append(f"--- Message {i} ---")
        parts.append(f"From: {msg.get('from_name', '')} <{msg.get('from_email', '')}>")
        parts.append(f"Date: {msg.get('date', '')}")
        body = _strip_boilerplate(_strip_quoted_reply(msg.get("body", "").strip()))
        parts.append(body)
        parts.append("")
    return JsonResponse({"formatted_text": "\n".join(parts), "subject": subject})


def drawer_session(request):
    """Return or create a session for the drawer.

    ?new=1 forces a fresh session.  Otherwise returns the most recent.
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
