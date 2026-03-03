from django import forms
from legacy.forms import TailwindFormMixin
from dashboard.choices import get_choices
from assets.models import PropertyOwnership, InvestmentParticipant, LoanParty
from .models import Stakeholder, StakeholderTab, ContactLog


class StakeholderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Stakeholder
        fields = ["name", "entity_type", "email", "phone", "organization",
                  "parent_organization", "trust_rating", "risk_rating", "notes_text"]
        widgets = {
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "parent_organization": "Firm",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entity_type"].widget = forms.Select(choices=get_choices("entity_type"))
        self.fields["parent_organization"].queryset = Stakeholder.objects.filter(entity_type="firm")


class ContactLogForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ContactLog
        fields = ["date", "method", "summary", "follow_up_needed", "follow_up_date"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "follow_up_date": forms.DateInput(attrs={"type": "date"}),
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["method"].widget = forms.Select(choices=get_choices("contact_method"))


class StakeholderTabForm(TailwindFormMixin, forms.Form):
    label = forms.CharField(max_length=100)
    entity_types = forms.MultipleChoiceField(
        choices=[],
        widget=forms.CheckboxSelectMultiple,
        required=False,
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
