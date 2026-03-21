from django import forms

from config.forms import TailwindFormMixin
from .models import Checklist, ChecklistItem


class ChecklistForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Checklist
        fields = ["name", "due_date"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Checklist name..."}),
            "due_date": forms.DateInput(attrs={"type": "date", "placeholder": "Due date (optional)"}),
        }


class ChecklistItemForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Add a checklist item..."}),
        }
