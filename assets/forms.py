from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from stakeholders.models import Stakeholder
from .models import (Aircraft, AircraftOwner, AssetTab, InsurancePolicy, Investment,
                     Lease, LeaseParty, Loan, LoanParty, PolicyHolder,
                     PropertyOwnership, RealEstate,
                     InvestmentParticipant, Vehicle, VehicleOwner)


class AssetTabForm(TailwindFormMixin, forms.Form):
    label = forms.CharField(max_length=100)
    asset_types = forms.MultipleChoiceField(
        choices=AssetTab.ASSET_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Select at least one asset type."},
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance:
            kwargs.setdefault("initial", {})
            kwargs["initial"]["label"] = instance.label
            kwargs["initial"]["asset_types"] = instance.asset_types
        super().__init__(*args, **kwargs)

    def save(self):
        if self.instance:
            self.instance.label = self.cleaned_data["label"]
            self.instance.asset_types = self.cleaned_data["asset_types"]
            self.instance.save()
            return self.instance
        tab = AssetTab(
            label=self.cleaned_data["label"],
            asset_types=self.cleaned_data["asset_types"],
        )
        last = AssetTab.objects.order_by("-sort_order").first()
        tab.sort_order = (last.sort_order + 1) if last else 0
        tab.save()
        return tab


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
        fields = ["name", "is_hard_money", "related_property", "related_investment",
                  "related_vehicle", "related_aircraft",
                  "borrower_description", "original_amount",
                  "current_balance", "interest_rate", "default_interest_rate",
                  "monthly_payment",
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
            "related_vehicle": "Vehicle",
            "related_aircraft": "Aircraft",
        }


class LoanPartyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LoanParty
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class InsurancePolicyForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Policyholder",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")

    field_order = [
        "name", "policy_number", "policy_type", "status",
        "carrier", "agent",
        "premium_amount", "premium_frequency", "deductible", "coverage_limit",
        "effective_date", "expiration_date", "auto_renew",
        "covered_properties", "covered_vehicles", "covered_aircraft", "notes_text",
        "initial_stakeholder", "initial_role",
    ]

    class Meta:
        model = InsurancePolicy
        fields = [
            "name", "policy_number", "policy_type", "status",
            "carrier", "agent",
            "premium_amount", "premium_frequency", "deductible", "coverage_limit",
            "effective_date", "expiration_date", "auto_renew",
            "covered_properties", "covered_vehicles", "covered_aircraft", "notes_text",
        ]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date"}),
            "expiration_date": forms.DateInput(attrs={"type": "date"}),
            "policy_type": forms.Select(),
            "covered_properties": forms.SelectMultiple(attrs={"size": 4}),
            "covered_vehicles": forms.SelectMultiple(attrs={"size": 4}),
            "covered_aircraft": forms.SelectMultiple(attrs={"size": 4}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["policy_type"].widget.choices = get_choices("policy_type")


class PolicyHolderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PolicyHolder
        fields = ["stakeholder", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class VehicleForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Owner",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")
    initial_percentage = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, label="Ownership %",
    )

    field_order = ["name", "vin", "year", "make", "model_name", "vehicle_type",
                   "color", "license_plate", "registration_state", "mileage",
                   "estimated_value", "acquisition_date", "status", "notes_text",
                   "initial_stakeholder", "initial_role", "initial_percentage"]

    class Meta:
        model = Vehicle
        fields = ["name", "vin", "year", "make", "model_name", "vehicle_type",
                  "color", "license_plate", "registration_state", "mileage",
                  "estimated_value", "acquisition_date", "status", "notes_text"]
        widgets = {
            "acquisition_date": forms.DateInput(attrs={"type": "date"}),
            "vehicle_type": forms.Select(),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle_type"].widget.choices = get_choices("vehicle_type")


class VehicleOwnerForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = VehicleOwner
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class AircraftForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Owner",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")
    initial_percentage = forms.DecimalField(
        max_digits=5, decimal_places=2, required=False, label="Ownership %",
    )

    field_order = ["name", "tail_number", "serial_number", "year", "make", "model_name",
                   "aircraft_type", "num_engines", "base_airport", "total_hours",
                   "estimated_value", "acquisition_date", "status",
                   "registration_country", "notes_text",
                   "initial_stakeholder", "initial_role", "initial_percentage"]

    class Meta:
        model = Aircraft
        fields = ["name", "tail_number", "serial_number", "year", "make", "model_name",
                  "aircraft_type", "num_engines", "base_airport", "total_hours",
                  "estimated_value", "acquisition_date", "status",
                  "registration_country", "notes_text"]
        widgets = {
            "acquisition_date": forms.DateInput(attrs={"type": "date"}),
            "aircraft_type": forms.Select(),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["aircraft_type"].widget.choices = get_choices("aircraft_type")


class AircraftOwnerForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = AircraftOwner
        fields = ["stakeholder", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class LeaseForm(TailwindFormMixin, forms.ModelForm):
    initial_stakeholder = forms.ModelChoiceField(
        queryset=Stakeholder.objects.all(), required=False, label="Initial Party",
    )
    initial_role = forms.CharField(max_length=100, required=False, label="Role")

    field_order = [
        "name", "related_property", "lease_type", "status",
        "start_date", "end_date", "monthly_rent", "security_deposit",
        "rent_due_day", "renewal_type", "renewal_terms", "escalation_rate",
        "notes_text",
        "initial_stakeholder", "initial_role",
    ]

    class Meta:
        model = Lease
        fields = [
            "name", "related_property", "lease_type", "status",
            "start_date", "end_date", "monthly_rent", "security_deposit",
            "rent_due_day", "renewal_type", "renewal_terms", "escalation_rate",
            "notes_text",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "lease_type": forms.Select(),
            "renewal_terms": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["lease_type"].widget.choices = get_choices("lease_type")


class LeasePartyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = LeaseParty
        fields = ["stakeholder", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class AssetPolicyLinkForm(TailwindFormMixin, forms.Form):
    policy = forms.ModelChoiceField(
        queryset=InsurancePolicy.objects.all(),
        label="Insurance Policy",
    )


class AssetLoanLinkForm(TailwindFormMixin, forms.Form):
    loan = forms.ModelChoiceField(
        queryset=Loan.objects.all(),
        label="Loan",
    )


class AssetNoteLinkForm(TailwindFormMixin, forms.Form):
    note = forms.ModelChoiceField(
        queryset=None,
        label="Note",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from notes.models import Note
        self.fields["note"].queryset = Note.objects.all()


class AssetLegalLinkForm(TailwindFormMixin, forms.Form):
    legal_matter = forms.ModelChoiceField(
        queryset=None,
        label="Legal Matter",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from legal.models import LegalMatter
        self.fields["legal_matter"].queryset = LegalMatter.objects.all()
