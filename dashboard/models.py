from django.db import models
from django.utils import timezone


CATEGORY_CHOICES = [
    ("entity_type", "Stakeholder Type"),
    ("contact_method", "Contact Method"),
    ("matter_type", "Legal Matter Type"),
    ("note_type", "Note Type"),
    ("policy_type", "Insurance Policy Type"),
    ("vehicle_type", "Vehicle Type"),
    ("aircraft_type", "Aircraft Type"),
    ("cashflow_category", "Cash Flow Category"),
    ("lease_type", "Lease Type"),
]


class ChoiceOption(models.Model):
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, db_index=True)
    value = models.CharField(max_length=30)
    label = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["category", "value"]
        ordering = ["category", "sort_order", "label"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.label}"


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
        "From email", default="noreply@controlcenter.local"
    )
    admin_email = models.EmailField(
        "Admin email (recipient)", default="admin@controlcenter.local"
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


class BackupSettings(models.Model):
    """Singleton model for automated backup configuration. Always use pk=1."""

    FREQUENCY_CHOICES = [
        ("D", "Daily"),
        ("H", "Hourly"),
        ("W", "Weekly"),
    ]

    enabled = models.BooleanField("Enable automated backups", default=True)
    frequency = models.CharField(
        max_length=1, choices=FREQUENCY_CHOICES, default="D"
    )
    time_hour = models.PositiveSmallIntegerField("Hour (0-23)", default=0)
    time_minute = models.PositiveSmallIntegerField("Minute (0-59)", default=0)
    retention_count = models.PositiveSmallIntegerField(
        "Backups to keep", default=7
    )

    class Meta:
        verbose_name = "Backup Settings"
        verbose_name_plural = "Backup Settings"

    def __str__(self):
        return "Backup Settings"

    @classmethod
    def load(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj


class SampleDataStatus(models.Model):
    """Singleton model tracking whether sample data is loaded. Always use pk=1."""

    is_loaded = models.BooleanField(default=False)
    manifest = models.JSONField(default=dict, blank=True)
    loaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Sample Data Status"
        verbose_name_plural = "Sample Data Status"

    def __str__(self):
        return "Sample Data Status"

    @classmethod
    def load(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
