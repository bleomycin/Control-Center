from django import forms
from legacy.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import Task, FollowUp


class TaskForm(TailwindFormMixin, forms.ModelForm):
    fu_create = forms.BooleanField(required=False, label="Create follow-up for this task")
    fu_method = forms.ChoiceField(required=False, label="Method")
    fu_follow_up_days = forms.IntegerField(
        required=False, initial=3, min_value=1, max_value=90,
        label="Remind after (days)",
    )
    fu_notes = forms.CharField(required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 2}))

    class Meta:
        model = Task
        fields = ["title", "description", "due_date", "reminder_date", "status",
                  "priority", "task_type", "related_stakeholder",
                  "related_legal_matter", "related_property"]
        widgets = {
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "reminder_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fu_method"].choices = get_choices("contact_method")


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
        fields = ["stakeholder", "outreach_date", "method", "follow_up_days", "notes_text"]
        widgets = {
            "outreach_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes_text": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "follow_up_days": "Remind after (days)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget = forms.Select(choices=get_choices("contact_method"))
