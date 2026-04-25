from django import forms

from config.forms import TailwindFormMixin
from .models import Checklist, ChecklistItem


class ChecklistForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Checklist
        fields = ["name", "due_date", "is_reference"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Checklist name..."}),
            "due_date": forms.DateInput(attrs={"type": "date", "title": "Due date (optional)"}),
            "is_reference": forms.HiddenInput(),
        }


class ChecklistItemForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ["title"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Add a checklist item..."}),
        }
