from django.contrib import messages
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from . import client as assistant_client
from .forms import AssistantSettingsForm, ChatInputForm
from .models import AssistantSettings, ChatMessage, ChatSession


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
    # Filter to only display-worthy messages (skip tool_data-only messages)
    display_messages = [
        m for m in messages
        if m.content or (m.tool_data and m.role == "assistant")
    ]

    form = ChatInputForm()

    return render(request, "assistant/chat.html", {
        "session": session,
        "sessions": sessions,
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

    # Filter to display-worthy messages
    display_messages = [
        m for m in new_messages
        if m.content or (m.tool_data and m.role == "assistant")
    ]

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
        sessions = ChatSession.objects.all()
        return render(request, "assistant/partials/_session_list.html", {
            "sessions": sessions,
            "session": session,
        })
    return redirect("assistant:chat_session", session_id=session.pk)


def prune_history(request, session_id):
    """Delete older messages, keeping the last N."""
    session = get_object_or_404(ChatSession, pk=session_id)
    keep = int(request.POST.get("keep", 20))

    message_ids = list(
        session.messages.order_by("-created_at").values_list("pk", flat=True)[keep:]
    )
    ChatMessage.objects.filter(pk__in=message_ids).delete()

    messages = session.messages.all()
    display_messages = [
        m for m in messages
        if m.content or (m.tool_data and m.role == "assistant")
    ]

    return render(request, "assistant/partials/_message_list.html", {
        "chat_messages": display_messages,
    })


def session_list(request):
    """Return the session list partial (for HTMX refresh)."""
    sessions = ChatSession.objects.all()
    current_id = request.GET.get("current")
    session = None
    if current_id:
        try:
            session = ChatSession.objects.get(pk=current_id)
        except ChatSession.DoesNotExist:
            pass
    return render(request, "assistant/partials/_session_list.html", {
        "sessions": sessions,
        "session": session,
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
