from django import forms
from legacy.forms import TailwindFormMixin
from stakeholders.models import Stakeholder
from .models import RealEstate, Investment, Loan, PropertyOwnership, InvestmentParticipant, LoanParty


class RealEstateForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Owner",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")
    initial_percentage = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, label="Ownership %",
    )

    field_order = ["name", "address", "jurisdiction", "property_type",
                   "estimated_value", "acquisition_date", "status", "notes_text",
                   "initial_stakeholder", "initial_role", "initial_percentage"]

    class Meta:
        model = RealEstate
        fields = ["name", "address", "jurisdiction", "property_type",
                  "estimated_value", "acquisition_date", "status", "notes_text"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "acquisition_date": forms.DateInput(attrs={"type": "date"}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class PropertyOwnershipForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PropertyOwnership
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class InvestmentForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Participant",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")
    initial_percentage = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, label="Ownership %",
    )

    field_order = ["name", "investment_type", "institution", "current_value", "notes_text",
                   "initial_stakeholder", "initial_role", "initial_percentage"]

    class Meta:
        model = Investment
        fields = ["name", "investment_type", "institution", "current_value", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class InvestmentParticipantForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = InvestmentParticipant
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class LoanForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Loan
        fields = ["name", "related_property", "related_investment",
                  "borrower_description", "original_amount",
                  "current_balance", "interest_rate", "monthly_payment",
                  "next_payment_date", "maturity_date", "collateral", "status", "notes_text"]
        widgets = {
            "next_payment_date": forms.DateInput(attrs={"type": "date"}),
            "maturity_date": forms.DateInput(attrs={"type": "date"}),
            "collateral": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "related_property": "Property",
            "related_investment": "Investment",
        }


class LoanPartyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LoanParty
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
