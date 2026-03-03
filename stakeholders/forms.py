from django import forms
from legacy.forms import TailwindFormMixin
from dashboard.choices import get_choices
from assets.models import PropertyOwnership, InvestmentParticipant, LoanParty
from .models import Stakeholder, ContactLog


class StakeholderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Stakeholder
        fields = ["name", "entity_type", "email", "phone", "organization",
                  "parent_organization", "trust_rating", "risk_rating", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "parent_organization": "Firm",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].widget = forms.Select(choices=get_choices("entity_type"))
        self.fields["parent_organization"].queryset = Stakeholder.objects.filter(entity_type="firm")


class ContactLogForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ContactLog
        fields = ["date", "method", "summary", "follow_up_needed", "follow_up_date"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget = forms.Select(choices=get_choices("contact_method"))


class StakeholderPropertyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PropertyOwnership
        fields = ["property", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class StakeholderInvestmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = InvestmentParticipant
        fields = ["investment", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class StakeholderLoanForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LoanParty
        fields = ["loan", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
