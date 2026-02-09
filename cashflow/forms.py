from django import forms
from blaine.forms import TailwindFormMixin
from .models import CashFlowEntry


class CashFlowEntryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CashFlowEntry
        fields = ["description", "amount", "entry_type", "category", "date",
                  "is_projected", "related_stakeholder", "related_property",
                  "related_loan", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes_text": forms.Textarea(attrs={"rows": 2}),
        }
