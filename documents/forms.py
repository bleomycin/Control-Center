from django import forms

from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import Document


class DocumentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Document
        fields = [
            "title", "category", "description", "date", "expiration_date",
            "gdrive_url", "gdrive_file_id", "gdrive_mime_type", "gdrive_file_name",
            "file",
            "related_property", "related_investment", "related_loan",
            "related_lease", "related_policy", "related_vehicle",
            "related_aircraft", "related_stakeholder", "related_legal_matter",
            "notes_text",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "expiration_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
            "file": forms.FileInput(),
            "gdrive_file_id": forms.HiddenInput(),
            "gdrive_mime_type": forms.HiddenInput(),
            "gdrive_file_name": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget = forms.Select(
            choices=[("", "---------")] + list(get_choices("document_category")),
            attrs=self.fields["category"].widget.attrs,
        )
        # Lazy-load FK choices to avoid circular imports
        from assets.models import (
            RealEstate, Investment, Loan, Lease, InsurancePolicy, Vehicle, Aircraft,
        )
        from stakeholders.models import Stakeholder
        from legal.models import LegalMatter

        self.fields["related_property"].queryset = RealEstate.objects.order_by("name")
        self.fields["related_investment"].queryset = Investment.objects.order_by("name")
        self.fields["related_loan"].queryset = Loan.objects.order_by("name")
        self.fields["related_lease"].queryset = Lease.objects.order_by("name")
        self.fields["related_policy"].queryset = InsurancePolicy.objects.order_by("name")
        self.fields["related_vehicle"].queryset = Vehicle.objects.order_by("name")
        self.fields["related_aircraft"].queryset = Aircraft.objects.order_by("name")
        self.fields["related_stakeholder"].queryset = Stakeholder.objects.order_by("name")
        self.fields["related_legal_matter"].queryset = LegalMatter.objects.order_by("title")


class GoogleDriveSetupForm(TailwindFormMixin, forms.ModelForm):
    """Form for entering Google Cloud OAuth2 credentials."""

    class Meta:
        from .models import GoogleDriveSettings
        model = GoogleDriveSettings
        fields = ["client_id", "client_secret", "api_key", "project_number", "picker_debug"]
        widgets = {
            "client_secret": forms.PasswordInput(attrs={"autocomplete": "off"}),
            "api_key": forms.PasswordInput(attrs={"autocomplete": "off"}),
        }
        labels = {
            "client_id": "Client ID",
            "client_secret": "Client Secret",
            "api_key": "API Key (for Picker)",
            "project_number": "Project Number",
            "picker_debug": "Enable Picker Debug Panel",
        }
        help_texts = {
            "client_id": "From Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client ID",
            "client_secret": "The corresponding client secret",
            "api_key": "API key with Google Picker API enabled (optional — needed for Picker)",
            "project_number": "From Google Cloud Console → IAM & Admin → Settings → Project number (numeric)",
            "picker_debug": "Show diagnostic debug panel and test buttons on the document form",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show placeholder when secrets already exist
        if self.instance and self.instance.client_secret:
            self.fields["client_secret"].widget.attrs["placeholder"] = "Leave blank to keep current"
        if self.instance and self.instance.api_key:
            self.fields["api_key"].widget.attrs["placeholder"] = "Leave blank to keep current"
        self.fields["client_secret"].required = False
        self.fields["api_key"].required = False

    def clean_client_secret(self):
        val = self.cleaned_data.get("client_secret")
        if not val and self.instance:
            return self.instance.client_secret
        return val

    def clean_api_key(self):
        val = self.cleaned_data.get("api_key")
        if not val and self.instance:
            return self.instance.api_key
        return val


class DocumentLinkForm(TailwindFormMixin, forms.Form):
    """Dropdown to pick an existing document for linking to an entity."""
    document = forms.ModelChoiceField(
        queryset=None,
        label="Document",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["document"].queryset = Document.objects.order_by("-date", "-created_at")
