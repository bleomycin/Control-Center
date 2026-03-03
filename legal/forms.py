from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import LegalMatter, Evidence


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
        fields = ["title", "description", "evidence_type", "date_obtained", "file", "url"]
        widgets = {
            "date_obtained": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "file": forms.FileInput(),
        }
