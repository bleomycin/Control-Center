from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choice_label, get_choices
from stakeholders.models import Stakeholder
from .models import Task, FollowUp, SubTask

DURATION_CHOICES = [
    ("", "---------"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (45, "45 minutes"),
    (60, "1 hour"),
    (90, "1.5 hours"),
    (120, "2 hours"),
    (180, "3 hours"),
    (240, "4 hours"),
]


def _grouped_stakeholder_choices():
    """Build optgroup-style choices grouped by entity type."""
    groups = {}
    for s in Stakeholder.objects.order_by("name"):
        label = get_choice_label("entity_type", s.entity_type)
        groups.setdefault(label, []).append((s.pk, s.name))
    choices = [("", "---------")]
    for group_label in sorted(groups):
        choices.append((group_label, groups[group_label]))
    return choices


class TaskForm(TailwindFormMixin, forms.ModelForm):
    fu_create = forms.BooleanField(required=False, label="Create follow-up for this task")
    fu_method = forms.ChoiceField(required=False, label="Method")
    fu_reminder_enabled = forms.BooleanField(required=False, label="Enable reminder")
    fu_follow_up_days = forms.IntegerField(
        required=False, initial=3, min_value=1, max_value=90,
        label="Remind after (days)",
    )
    fu_notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Task
        fields = ["title", "direction", "description", "task_type", "due_date", "due_time", "duration_minutes",
                  "reminder_date", "status",
                  "priority", "assigned_to", "related_stakeholders",
                  "related_legal_matter", "related_property",
                  "is_recurring", "recurrence_rule"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "duration_minutes": forms.Select(choices=DURATION_CHOICES),
            "reminder_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 6}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": "5"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fu_method"].choices = get_choices("contact_method")
        self.fields["related_stakeholders"].choices = _grouped_stakeholder_choices()
        self.fields["assigned_to"].queryset = Stakeholder.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("due_time") and not cleaned.get("due_date"):
            self.add_error("due_time", "A due date is required when setting a time.")
        if cleaned.get("is_recurring") and not cleaned.get("recurrence_rule"):
            self.add_error("recurrence_rule", "Select a recurrence schedule.")
        if cleaned.get("is_recurring") and not cleaned.get("due_date"):
            self.add_error("due_date", "A due date is required for recurring tasks.")
        return cleaned


class QuickTaskForm(TailwindFormMixin, forms.ModelForm):
    QUICK_TYPE_CHOICES = [
        ("one_time", "One-Time"),
        ("reference", "Reference"),
        ("meeting", "Meeting"),
        ("appointment", "Appointment"),
    ]

    task_type = forms.ChoiceField(choices=QUICK_TYPE_CHOICES, initial="one_time", label="Type")
    provider = forms.ModelChoiceField(
        queryset=None, required=False, label="Provider",
    )

    class Meta:
        model = Task
        fields = ["title", "due_date", "due_time", "duration_minutes", "priority", "description"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "duration_minutes": forms.Select(choices=DURATION_CHOICES),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Location, link, or other details..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from healthcare.models import Provider
        self.fields["provider"].queryset = Provider.objects.filter(status="active")
        # Reorder so task_type appears after title
        self.order_fields(["title", "task_type", "due_date", "due_time", "duration_minutes",
                           "provider", "priority", "description"])

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("due_time") and not cleaned.get("due_date"):
            self.add_error("due_time", "A due date is required when setting a time.")
        if cleaned.get("task_type") == "appointment" and not cleaned.get("due_date"):
            self.add_error("due_date", "A date is required for appointments.")
        return cleaned


class FollowUpForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ["stakeholder", "outreach_date", "method", "reminder_enabled", "follow_up_days", "notes_text"]
        widgets = {
            "outreach_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "method": forms.Select(),
            "notes_text": forms.Textarea(attrs={"rows": 2, "class": "auto-grow-textarea"}),
        }
        labels = {
            "reminder_enabled": "Enable reminder",
            "follow_up_days": "Remind after (days)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget.choices = get_choices("contact_method")


class SubTaskForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = SubTask
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"placeholder": "Add a checklist item..."})}
