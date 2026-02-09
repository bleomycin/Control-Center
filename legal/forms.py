from django import forms
from blaine.forms import TailwindFormMixin
from .models import LegalMatter, Evidence


class LegalMatterForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LegalMatter
        fields = ["title", "case_number", "matter_type", "status", "jurisdiction",
                  "court", "filing_date", "description", "attorneys",
                  "related_stakeholders", "related_properties"]
        widgets = {
            "filing_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "attorneys": forms.SelectMultiple(attrs={"size": 4}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": 4}),
            "related_properties": forms.SelectMultiple(attrs={"size": 4}),
        }


class EvidenceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Evidence
        fields = ["title", "description", "evidence_type", "date_obtained", "file"]
        widgets = {
            "date_obtained": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }
