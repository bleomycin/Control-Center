from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from stakeholders.models import Stakeholder
from .models import CaseLog, FirmEngagement, LegalMatter, Evidence, LegalCommunication, LegalChecklistItem


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
            "summary": forms.Textarea(attrs={"rows": 8}),
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


class CaseLogForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CaseLog
        fields = ["stakeholder", "source_name", "text"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 2, "placeholder": "What happened..."}),
            "source_name": forms.TextInput(attrs={"placeholder": "Name (if not a stakeholder)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stakeholder"].queryset = Stakeholder.objects.order_by("name")
        self.fields["stakeholder"].required = False


class FirmEngagementForm(TailwindFormMixin, forms.ModelForm):
    create_new = forms.BooleanField(required=False, widget=forms.HiddenInput())
    new_firm_name = forms.CharField(required=False, max_length=255,
                                    widget=forms.TextInput(attrs={"placeholder": "Firm name"}))
    new_firm_email = forms.CharField(required=False, max_length=254,
                                     widget=forms.EmailInput(attrs={"placeholder": "Email (optional)"}))
    new_firm_phone = forms.CharField(required=False, max_length=50,
                                     widget=forms.TextInput(attrs={"placeholder": "Phone (optional)"}))

    class Meta:
        model = FirmEngagement
        fields = ["firm", "status", "initial_contact_date", "response_date",
                  "decision_date", "referred_by", "scope", "notes"]
        widgets = {
            "initial_contact_date": forms.DateInput(attrs={"type": "date"}),
            "response_date": forms.DateInput(attrs={"type": "date"}),
            "decision_date": forms.DateInput(attrs={"type": "date"}),
            "scope": forms.Textarea(attrs={"rows": 2, "placeholder": "What aspect of the case does this firm cover?"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Additional notes..."}),
        }

    def __init__(self, *args, **kwargs):
        self.legal_matter = kwargs.pop("legal_matter", None)
        super().__init__(*args, **kwargs)
        self.fields["firm"].queryset = Stakeholder.objects.order_by("name")
        self.fields["firm"].required = False
        if self.legal_matter:
            self.fields["referred_by"].queryset = FirmEngagement.objects.filter(
                legal_matter=self.legal_matter
            ).select_related("firm")
        else:
            self.fields["referred_by"].queryset = FirmEngagement.objects.none()
        self.fields["referred_by"].required = False

    def clean(self):
        cleaned = super().clean()
        create_new = cleaned.get("create_new")
        firm = cleaned.get("firm")
        new_name = cleaned.get("new_firm_name", "").strip()

        if create_new:
            if not new_name:
                self.add_error("new_firm_name", "Firm name is required.")
        elif not firm:
            self.add_error("firm", "Select a firm or create a new one.")
        return cleaned

    def save(self, commit=True):
        if self.cleaned_data.get("create_new"):
            firm = Stakeholder.objects.create(
                name=self.cleaned_data["new_firm_name"].strip(),
                entity_type="firm",
                firm_type="law",
                email=self.cleaned_data.get("new_firm_email", "").strip(),
                phone=self.cleaned_data.get("new_firm_phone", "").strip(),
            )
            self.instance.firm = firm
        return super().save(commit=commit)
