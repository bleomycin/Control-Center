from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from assets.models import (AircraftOwner, InsurancePolicy, InvestmentParticipant,
                           LoanParty, PolicyHolder, PropertyOwnership, VehicleOwner)
from .models import Relationship, Stakeholder, StakeholderTab, ContactLog


class StakeholderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Stakeholder
        fields = ["name", "entity_type", "email", "phone", "organization",
                  "parent_organization", "trust_rating", "risk_rating", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
            "entity_type": forms.Select(),
        }
        labels = {
            "parent_organization": "Firm",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].widget.choices = get_choices("entity_type")
        self.fields["parent_organization"].queryset = Stakeholder.objects.filter(entity_type="firm")


class ContactLogForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ContactLog
        fields = ["date", "method", "summary", "follow_up_needed", "follow_up_date"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
            "method": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget.choices = get_choices("contact_method")


class StakeholderTabForm(TailwindFormMixin, forms.Form):
    label = forms.CharField(max_length=100)
    entity_types = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Select at least one entity type."},
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance:
            kwargs.setdefault("initial", {})
            kwargs["initial"]["label"] = instance.label
            kwargs["initial"]["entity_types"] = instance.entity_types
        super().__init__(*args, **kwargs)
        # Exclude "firm" since the Firms & Teams tab handles that
        choices = [(v, l) for v, l in get_choices("entity_type") if v != "firm"]
        self.fields["entity_types"].choices = choices

    def save(self):
        if self.instance:
            self.instance.label = self.cleaned_data["label"]
            self.instance.entity_types = self.cleaned_data["entity_types"]
            self.instance.save()
            return self.instance
        tab = StakeholderTab(
            label=self.cleaned_data["label"],
            entity_types=self.cleaned_data["entity_types"],
        )
        # Set sort_order after existing tabs
        last = StakeholderTab.objects.order_by("-sort_order").first()
        tab.sort_order = (last.sort_order + 1) if last else 0
        tab.save()
        return tab


class EmployeeAssignForm(TailwindFormMixin, forms.Form):
    stakeholder = forms.ModelChoiceField(queryset=Stakeholder.objects.none())

    def __init__(self, *args, firm=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Stakeholder.objects.exclude(entity_type="firm")
        if firm:
            qs = qs.exclude(parent_organization=firm)
        self.fields["stakeholder"].queryset = qs


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


class StakeholderVehicleForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = VehicleOwner
        fields = ["vehicle", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class StakeholderAircraftForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = AircraftOwner
        fields = ["aircraft", "ownership_percentage", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class StakeholderPolicyForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = PolicyHolder
        fields = ["policy", "role", "notes"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class StakeholderRelationshipForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Relationship
        fields = ["to_stakeholder", "relationship_type", "description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {
            "to_stakeholder": "Stakeholder",
        }

    def validate_unique(self):
        exclude = self._get_validation_exclusions()
        exclude.discard("from_stakeholder")
        try:
            self.instance.validate_unique(exclude=exclude)
        except forms.ValidationError as e:
            self._update_errors(e)
