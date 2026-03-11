from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from stakeholders.models import Stakeholder
from .models import LegalMatter, Evidence, LegalCommunication, LegalChecklistItem


class LegalMatterForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LegalMatter
        fields = ["title", "case_number", "matter_type", "status", "jurisdiction",
                  "court", "filing_date", "next_hearing_date",
                  "settlement_amount", "judgment_amount", "outcome",
                  "description", "attorneys",
                  "related_stakeholders", "related_properties",
                  "related_investments", "related_loans", "related_vehicles",
                  "related_aircraft", "related_policies", "related_leases"]
        widgets = {
            "filing_date": forms.DateInput(attrs={"type": "date"}),
            "next_hearing_date": forms.DateInput(attrs={"type": "date"}),
            "outcome": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "matter_type": forms.Select(),
            "attorneys": forms.SelectMultiple(attrs={"size": 4}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": 4}),
            "related_properties": forms.SelectMultiple(attrs={"size": 4}),
            "related_investments": forms.SelectMultiple(attrs={"size": 4}),
            "related_loans": forms.SelectMultiple(attrs={"size": 4}),
            "related_vehicles": forms.SelectMultiple(attrs={"size": 4}),
            "related_aircraft": forms.SelectMultiple(attrs={"size": 4}),
            "related_policies": forms.SelectMultiple(attrs={"size": 4}),
            "related_leases": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["matter_type"].widget.choices = get_choices("matter_type")


class EvidenceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ["title", "description", "evidence_type", "date_obtained", "file", "gdrive_url", "url"]
        widgets = {
            "date_obtained": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "file": forms.FileInput(),
        }


class LegalCommunicationForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LegalCommunication
        fields = ["stakeholder", "date", "direction", "method", "subject", "summary",
                  "follow_up_needed", "follow_up_date", "file", "gdrive_url"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
            "method": forms.Select(),
            "file": forms.FileInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget.choices = get_choices("contact_method")
        self.fields["stakeholder"].queryset = Stakeholder.objects.order_by("name")


class LegalChecklistForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LegalChecklistItem
        fields = ["title"]
        widgets = {"title": forms.TextInput(attrs={"placeholder": "Add a checklist item..."})}
