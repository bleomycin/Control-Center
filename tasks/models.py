from django.db import models
from django.urls import reverse


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
    ]

    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    reminder_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="not_started")
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    task_type = models.CharField(max_length=10, choices=TASK_TYPE_CHOICES, default="one_time")
    related_stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tasks",
    )
    related_legal_matter = models.ForeignKey(
        "legal.LegalMatter", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tasks",
    )
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("tasks:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["due_date", "-priority"]


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
        "stakeholders.Stakeholder", on_delete=models.CASCADE, related_name="follow_ups",
    )
    outreach_date = models.DateTimeField()
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    response_received = models.BooleanField(default=False)
    response_date = models.DateTimeField(null=True, blank=True)
    notes_text = models.TextField(blank=True)

    def __str__(self):
        return f"Follow-up: {self.task} → {self.stakeholder} ({self.outreach_date:%Y-%m-%d})"

    def get_absolute_url(self):
        return reverse("tasks:detail", kwargs={"pk": self.task.pk})

    class Meta:
        ordering = ["-outreach_date"]
