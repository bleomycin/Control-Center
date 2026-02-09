from django.db import models
from django.urls import reverse


class Note(models.Model):
    NOTE_TYPE_CHOICES = [
        ("call", "Call"),
        ("email", "Email"),
        ("meeting", "Meeting"),
        ("research", "Research"),
        ("legal_update", "Legal Update"),
        ("general", "General"),
    ]

    title = models.CharField(max_length=255)
    content = models.TextField()
    date = models.DateTimeField()
    note_type = models.CharField(max_length=15, choices=NOTE_TYPE_CHOICES, default="general")
    participants = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="notes_as_participant",
    )
    related_stakeholders = models.ManyToManyField(
        "stakeholders.Stakeholder", blank=True, related_name="notes",
    )
    related_legal_matters = models.ManyToManyField(
        "legal.LegalMatter", blank=True, related_name="notes",
    )
    related_properties = models.ManyToManyField(
        "assets.RealEstate", blank=True, related_name="notes",
    )
    related_tasks = models.ManyToManyField(
        "tasks.Task", blank=True, related_name="notes",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("notes:detail", kwargs={"pk": self.pk})

    class Meta:
        ordering = ["-date"]


class Attachment(models.Model):
    note = models.ForeignKey(Note, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="attachments/")
    description = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description or self.file.name

    def get_absolute_url(self):
        return reverse("notes:detail", kwargs={"pk": self.note.pk})
