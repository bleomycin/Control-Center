from django import forms
from blaine.forms import TailwindFormMixin
from .models import Stakeholder, ContactLog


class StakeholderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Stakeholder
        fields = ["name", "entity_type", "email", "phone", "organization",
                  "trust_rating", "risk_rating", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class ContactLogForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ContactLog
        fields = ["date", "method", "summary", "follow_up_needed", "follow_up_date"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
        }
