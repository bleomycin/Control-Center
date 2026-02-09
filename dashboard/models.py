from django.db import models


class Notification(models.Model):
    LEVEL_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("critical", "Critical"),
    ]

    message = models.CharField(max_length=500)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, default="info")
    link = models.CharField(max_length=500, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.message[:50]


class EmailSettings(models.Model):
    """Singleton model for SMTP email configuration. Always use pk=1."""

    smtp_host = models.CharField("SMTP host", max_length=255, blank=True, default="")
    smtp_port = models.PositiveIntegerField("SMTP port", default=587)
    use_tls = models.BooleanField("Use TLS", default=True)
    use_ssl = models.BooleanField("Use SSL", default=False)
    username = models.CharField("Username", max_length=255, blank=True, default="")
    password = models.CharField("Password", max_length=255, blank=True, default="")
    from_email = models.EmailField(
        "From email", default="noreply@blaine.local"
    )
    admin_email = models.EmailField(
        "Admin email (recipient)", default="admin@blaine.local"
    )
    notifications_enabled = models.BooleanField(
        "Enable email notifications", default=False
    )

    class Meta:
        verbose_name = "Email Settings"
        verbose_name_plural = "Email Settings"

    def __str__(self):
        return "Email Settings"

    @classmethod
    def load(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj

    def is_configured(self):
        """True when minimum SMTP fields are populated."""
        return bool(self.smtp_host and self.from_email and self.admin_email)
