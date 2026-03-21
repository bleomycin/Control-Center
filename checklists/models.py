from django.db import models
from django.utils import timezone


class Checklist(models.Model):
    """Named checklist container linked to any entity via explicit nullable FKs."""

    name = models.CharField(max_length=255)

    # Entity links (nullable FKs — same pattern as Document/EmailLink)
    related_stakeholder = models.ForeignKey(
        "stakeholders.Stakeholder", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="checklists",
    )
    related_task = models.ForeignKey(
        "tasks.Task", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="checklists",
    )
    related_note = models.ForeignKey(
        "notes.Note", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="checklists",
    )
    related_property = models.ForeignKey(
        "assets.RealEstate", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="checklists",
    )
    related_legal_matter = models.ForeignKey(
        "legal.LegalMatter", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="checklists",
    )

    due_date = models.DateField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        entity = self.linked_entity
        if entity:
            return entity.get_absolute_url()
        return "/"

    @property
    def linked_entity(self):
        """Return the first non-null related entity."""
        for field_name in (
            "related_stakeholder", "related_task", "related_note",
            "related_property", "related_legal_matter",
        ):
            obj = getattr(self, field_name, None)
            if obj is not None:
                return obj
        return None

    @property
    def is_overdue(self):
        return self.due_date is not None and self.due_date < timezone.localdate()

    @property
    def is_due_soon(self):
        """Due within the next 7 days."""
        if not self.due_date:
            return False
        today = timezone.localdate()
        from datetime import timedelta
        return today <= self.due_date <= today + timedelta(days=7)


class ChecklistItem(models.Model):
    """Individual checklist line item with completion tracking."""

    checklist = models.ForeignKey(
        Checklist, on_delete=models.CASCADE, related_name="items",
    )
    title = models.CharField(max_length=255)
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title
