from django.db import models


class AssistantSettings(models.Model):
    """Singleton settings for the AI assistant (pk=1)."""

    MODEL_CHOICES = [
        ("claude-sonnet-4-6", "Claude Sonnet 4.6 (recommended)"),
        ("claude-haiku-4-5-20251001", "Claude Haiku 4.5 (fastest, cheapest)"),
        ("claude-opus-4-6", "Claude Opus 4.6 (most capable)"),
    ]

    owner_name = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Your name, so the assistant knows not to create a stakeholder for you.",
    )
    api_key = models.CharField(max_length=255, blank=True, default="")
    model = models.CharField(max_length=100, default="claude-sonnet-4-6")
    max_tokens = models.PositiveIntegerField(default=8192)
    temperature = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.0,
        help_text="0.0 = deterministic, 1.0 = default, 2.0 = maximum creativity",
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

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
        """Strip the [Context: ...] prefix injected by the drawer for display."""
        if self.content and self.content.startswith("[Context:"):
            idx = self.content.find("]")
            if idx > -1:
                return self.content[idx + 1 :].strip()
        return self.content

    def __str__(self):
        return f"{self.role}: {self.content[:50]}"
