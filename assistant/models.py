import json

from django.db import models


class AssistantSettings(models.Model):
    """Singleton settings for the AI assistant (pk=1)."""

    # Suggested model ids for the settings datalist (a free-text field — any
    # valid Anthropic model id can be typed). Not a field `choices=` kwarg,
    # so editing this list never needs a migration. Current ids confirmed
    # 2026-07-10; think/max modes pin their own models in client.MODE_CONFIGS
    # regardless of this setting.
    MODEL_CHOICES = [
        ("claude-sonnet-5", "Claude Sonnet 5 (recommended)"),
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 (previous generation)"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (fastest, cheapest)"),
        ("claude-opus-4-8", "Claude Opus 4.8 (most capable)"),
    ]

    owner_name = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Your name, so the assistant knows not to create a stakeholder for you.",
    )
    api_key = models.CharField(max_length=255, blank=True, default="")
    model = models.CharField(max_length=100, default="claude-sonnet-5")
    # Sized for Sonnet 5's tokenizer (~30% more tokens per text than 4.x);
    # 12288 ≈ the old 8192 in 4.6-equivalent output.
    max_tokens = models.PositiveIntegerField(default=12288)
    temperature = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.0,
        help_text="0.0 = deterministic, 1.0 = default, 2.0 = maximum creativity",
    )
    default_reminder_minutes = models.PositiveIntegerField(
        default=60,
        help_text="Default reminder (minutes before due time) when creating tasks. 0 = no auto-reminder.",
    )

    class Meta:
        verbose_name = "Assistant Settings"
        verbose_name_plural = "Assistant Settings"

    def __str__(self):
        if self.api_key:
            masked = self.api_key[:8] + "..." + self.api_key[-4:] if len(self.api_key) > 12 else "***"
            return f"Assistant ({self.model}, key: {masked})"
        return "Assistant (not configured)"

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_effective_api_key(self):
        """Return the API key from DB settings, falling back to env var."""
        import os
        return self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")


class ChatSession(models.Model):
    title = models.CharField(max_length=255, default="New Chat")
    is_pinned = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "sort_order", "-updated_at"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        from django.urls import reverse
        return reverse("assistant:chat_session", kwargs={"session_id": self.pk})


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("assistant", "Assistant"),
    ]

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(blank=True)
    tool_data = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    @property
    def display_content(self):
        """Strip [AttachedEmail:...], [AttachedDriveFiles], and [Context:...]
        prefixes for display.

        The strips run in order: email → drive → context. Per the marker
        convention (see Plan 01-01 / CONTEXT.md D-10), an [AttachedEmail]
        block always precedes any [AttachedDriveFiles] block, which in turn
        precedes any [Context:] hint, which precedes the user's typed text.
        """
        text = self.content or ""
        if text.startswith("[AttachedEmails]"):
            end_marker = "[/AttachedEmails]"
            idx = text.find(end_marker)
            if idx > -1:
                text = text[idx + len(end_marker):].strip()
        if text.startswith("[AttachedEmail:"):
            end_marker = "[/AttachedEmail]"
            idx = text.find(end_marker)
            if idx > -1:
                text = text[idx + len(end_marker):].strip()
        if text.startswith("[AttachedDriveFiles]"):
            end_marker = "[/AttachedDriveFiles]"
            idx = text.find(end_marker)
            if idx > -1:
                text = text[idx + len(end_marker):].strip()
        if text.startswith("[Context:"):
            idx = text.find("]")
            if idx > -1:
                text = text[idx + 1:].strip()
        return text

    @property
    def attached_drive_files(self):
        """Parse the [AttachedDriveFiles] block from content and return the
        list of file dicts. Returns [] if absent, malformed JSON, or missing
        close marker. Never raises.
        """
        text = self.content or ""
        open_marker = "[AttachedDriveFiles]"
        close_marker = "[/AttachedDriveFiles]"
        i = text.find(open_marker)
        if i < 0:
            return []
        j = text.find(close_marker, i)
        if j < 0:
            return []
        json_text = text[i + len(open_marker):j].strip()
        try:
            parsed = json.loads(json_text)
        except (ValueError, TypeError):
            return []
        return parsed if isinstance(parsed, list) else []

    @property
    def attached_email_summary(self):
        """Parse the [AttachedEmail:{json}] header from content and return
        {subject, message_count}, or None if absent or malformed.

        Format: [AttachedEmail:{...json header...}]\\n...body...\\n[/AttachedEmail]\\n
        """
        text = self.content or ""
        if not text.startswith("[AttachedEmail:"):
            return None
        # Find the closing ] of the JSON header — looks for ']\n' since the
        # convention places the closing bracket immediately before a newline.
        bracket_end = text.find("]\n", len("[AttachedEmail:"))
        if bracket_end < 0:
            return None
        json_text = text[len("[AttachedEmail:"):bracket_end]
        try:
            meta = json.loads(json_text)
        except (ValueError, TypeError):
            return None
        if not isinstance(meta, dict):
            return None
        return {
            "subject": meta.get("subject", "(no subject)"),
            "message_count": meta.get("message_count", 1),
        }

    @property
    def attached_email_summaries(self):
        """Parse plural email attachments and return display summaries.

        New messages use:
        [AttachedEmails]
        [{...}, {...}]
        [/AttachedEmails]

        Existing history may still use the legacy single-email marker, so
        this property wraps that legacy summary in a one-item list.
        """
        text = self.content or ""
        open_marker = "[AttachedEmails]"
        close_marker = "[/AttachedEmails]"
        i = text.find(open_marker)
        if i >= 0:
            j = text.find(close_marker, i)
            if j < 0:
                return []
            json_text = text[i + len(open_marker):j].strip()
            try:
                parsed = json.loads(json_text)
            except (ValueError, TypeError):
                return []
            if not isinstance(parsed, list):
                return []
            summaries = []
            for item in parsed:
                if not isinstance(item, dict):
                    continue
                summaries.append({
                    "subject": item.get("subject", "(no subject)"),
                    "message_count": item.get("message_count", 1),
                })
            return summaries

        legacy_summary = self.attached_email_summary
        return [legacy_summary] if legacy_summary else []

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"


class AssistantTurn(models.Model):
    """Server-side lifecycle of one streamed assistant turn.

    The SSE connection and the turn are deliberately decoupled: when the
    browser connection is severed mid-turn (proxy abort, network fault), the
    server keeps working and persists the answer (see client._with_heartbeat).
    This row is what lets a reconnecting client tell the difference between
    "the stream died but the assistant is still working" and "the turn
    finished/failed while I was gone" — process memory can't do that across
    gunicorn workers, the DB can.
    """

    STATE_RUNNING = "running"
    STATE_COMPLETED = "completed"
    STATE_FAILED = "failed"
    STATE_ABANDONED = "abandoned"
    STATE_CHOICES = [
        (STATE_RUNNING, "Running"),
        (STATE_COMPLETED, "Completed"),
        (STATE_FAILED, "Failed"),
        (STATE_ABANDONED, "Abandoned"),
    ]

    # A running turn whose worker hasn't touched updated_at in this long is
    # presumed dead (container restart mid-turn). A dedicated toucher thread
    # refreshes the row every TURN_TOUCH_INTERVAL_SECONDS for the worker's
    # whole lifetime (client._with_heartbeat), independent of produced
    # frames, so this is several multiples of that cadence.
    STALE_AFTER_SECONDS = 180

    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="turns"
    )
    state = models.CharField(
        max_length=10, choices=STATE_CHOICES, default=STATE_RUNNING
    )
    client_disconnected = models.BooleanField(default=False)
    confirm_required = models.BooleanField(default=False)
    request_ids = models.JSONField(default=list, blank=True)
    final_message = models.ForeignKey(
        ChatMessage, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one RUNNING turn per session, enforced where it can't
            # race: two concurrent sends both passing an application-level
            # pre-check would interleave their ChatMessage writes and corrupt
            # tool pairing (the Phase 2 bug class from a different cause).
            # The admission path (views.stream_message_view) creates the turn
            # first and treats IntegrityError as "busy".
            models.UniqueConstraint(
                fields=["session"],
                condition=models.Q(state="running"),
                name="one_running_turn_per_session",
            ),
        ]

    @property
    def is_stale(self):
        from django.utils import timezone
        return (
            timezone.now() - self.updated_at
        ).total_seconds() > self.STALE_AFTER_SECONDS

    def __str__(self):
        return f"Turn {self.pk} ({self.state}) for session {self.session_id}"
