from django import forms
from legacy.forms import TailwindFormMixin
from .models import RealEstate, Investment, Loan, PropertyOwnership, InvestmentParticipant, LoanParty


class RealEstateForm(TailwindFormMixin, forms.ModelForm):
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
        fields = ["name", "borrower_description", "original_amount",
                  "current_balance", "interest_rate", "monthly_payment",
                  "next_payment_date", "maturity_date", "collateral", "status", "notes_text"]
        widgets = {
            "next_payment_date": forms.DateInput(attrs={"type": "date"}),
            "maturity_date": forms.DateInput(attrs={"type": "date"}),
            "collateral": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class LoanPartyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LoanParty
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
