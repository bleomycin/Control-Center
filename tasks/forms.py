from django import forms
from legacy.forms import TailwindFormMixin
from dashboard.choices import get_choice_label, get_choices
from stakeholders.models import Stakeholder
from .models import Task, FollowUp, SubTask


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
        fields = ["title", "direction", "description", "task_type", "due_date", "due_time", "reminder_date", "status",
                  "priority", "related_stakeholders",
                  "related_legal_matter", "related_property",
                  "is_recurring", "recurrence_rule"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "due_time": forms.TimeInput(attrs={"type": "time"}),
            "reminder_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": "5"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fu_method"].choices = get_choices("contact_method")
        self.fields["related_stakeholders"].choices = _grouped_stakeholder_choices()

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
    class Meta:
        model = Task
        fields = ["title", "due_date", "priority"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }


class FollowUpForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = FollowUp
        fields = ["stakeholder", "outreach_date", "method", "reminder_enabled", "follow_up_days", "notes_text"]
        widgets = {
            "outreach_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes_text": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "reminder_enabled": "Enable reminder",
            "follow_up_days": "Remind after (days)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget = forms.Select(choices=get_choices("contact_method"))


class SubTaskForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = SubTask
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"placeholder": "Add a checklist item..."})}
