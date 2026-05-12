from datetime import timedelta

from django.db import models
from django.urls import reverse
from django.utils import timezone


class Task(models.Model):
    STATUS_CHOICES = [
        ("not_started", "Not Started"),
        ("in_progress", "In Progress"),
        ("waiting", "Waiting"),
        ("complete", "Complete"),
    ]
    PRIORITY_CHOICES = [
        ("critical", "Critical"),
        ("high", "High"),
        ("medium", "Medium"),
        ("low", "Low"),
    ]
    TASK_TYPE_CHOICES = [
        ("one_time", "One-Time"),
        ("reference", "Reference"),
        ("meeting", "Meeting"),
    ]
    DIRECTION_CHOICES = [
        ("personal", "Personal"),
        ("outbound", "Outbound Request"),
        ("inbound", "Inbound Request"),
    ]
    RECURRENCE_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("biweekly", "Every 2 Weeks"),
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True, db_index=True)
    due_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    reminder_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started", db_index=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    task_type = models.CharField(max_length=10, choices=TASK_TYPE_CHOICES, default="one_time")
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES, default="personal")
    related_stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="tasks",
    )
    related_legal_matter = models.ForeignKey(
        "legal.LegalMatter", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tasks",
    )
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tasks",
    )
    assigned_to = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="assigned_tasks",
    )
    meeting_url = models.URLField(max_length=2000, blank=True, verbose_name="Meeting link")
    meeting_id = models.CharField(max_length=50, blank=True, verbose_name="Meeting ID")
    meeting_passcode = models.CharField(max_length=50, blank=True, verbose_name="Passcode")
    location = models.CharField(max_length=255, blank=True)
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=15, choices=RECURRENCE_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    @property
    def is_meeting(self):
        return self.task_type == "meeting"

    @property
    def has_stale_followups(self):
        if hasattr(self, '_prefetched_objects_cache') and 'follow_ups' in self._prefetched_objects_cache:
            return any(fu.is_stale for fu in self.follow_ups.all())
        return any(fu.is_stale for fu in self.follow_ups.filter(response_received=False, reminder_enabled=True))

    @property
    def scheduled_datetime_str(self):
        if self.due_date and self.due_time:
            return f"{self.due_date.isoformat()}T{self.due_time.strftime('%H:%M:%S')}"
        elif self.due_date:
            return self.due_date.isoformat()
        return ""

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("tasks:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["due_date", "-priority"]


class SubTask(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="subtasks")
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title


class FollowUp(models.Model):
    METHOD_CHOICES = [
        ("call", "Call"),
        ("email", "Email"),
        ("text", "Text"),
        ("meeting", "Meeting"),
        ("other", "Other"),
    ]

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="follow_ups")
    stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="follow_ups",
    )
    outreach_date = models.DateTimeField()
    method = models.CharField(max_length=30)
    reminder_enabled = models.BooleanField(default=False)
    follow_up_days = models.PositiveIntegerField(default=3)
    response_received = models.BooleanField(default=False)
    response_date = models.DateTimeField(null=True, blank=True)
    response_notes = models.TextField(blank=True)
    notes_text = models.TextField(blank=True)

    @property
    def reminder_due_date(self):
        return self.outreach_date + timedelta(days=self.follow_up_days)

    @property
    def is_stale(self):
        return self.reminder_enabled and not self.response_received and timezone.now() > self.reminder_due_date

    def __str__(self):
        return f"Follow-up: {self.task} → {self.stakeholder} ({self.outreach_date:%Y-%m-%d})"

    def get_absolute_url(self):
        return reverse("tasks:detail", kwargs={"pk": self.task.pk})

    class Meta:
        ordering = ["-outreach_date"]


class TaskLink(models.Model):
    """A reference link attached to a task."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="links")
    url = models.URLField(max_length=2000)
    label = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.label or self.url

    class Meta:
        ordering = ["created_at"]
