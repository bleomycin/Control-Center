from django import forms
from blaine.forms import TailwindFormMixin
from .models import RealEstate, Investment, Loan


class RealEstateForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = RealEstate
        fields = ["name", "address", "jurisdiction", "property_type",
                  "estimated_value", "acquisition_date", "status", "stakeholder", "notes_text"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "acquisition_date": forms.DateInput(attrs={"type": "date"}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class InvestmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Investment
        fields = ["name", "investment_type", "institution", "current_value",
                  "stakeholder", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class LoanForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Loan
        fields = ["name", "lender", "borrower_description", "original_amount",
                  "current_balance", "interest_rate", "monthly_payment",
                  "next_payment_date", "maturity_date", "collateral", "status", "notes_text"]
        widgets = {
            "next_payment_date": forms.DateInput(attrs={"type": "date"}),
            "maturity_date": forms.DateInput(attrs={"type": "date"}),
            "collateral": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }
