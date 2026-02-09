from django import forms
from blaine.forms import TailwindFormMixin
from .models import Task, FollowUp


class TaskForm(TailwindFormMixin, forms.ModelForm):
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
        fields = ["stakeholder", "outreach_date", "method", "response_received",
                  "response_date", "notes_text"]
        widgets = {
            "outreach_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "response_date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "notes_text": forms.Textarea(attrs={"rows": 2}),
        }
