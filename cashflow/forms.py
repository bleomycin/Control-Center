from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import CashFlowEntry


class CashFlowEntryForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = CashFlowEntry
        fields = ["description", "amount", "entry_type", "category", "date",
                  "is_projected", "is_recurring", "recurrence_rule",
                  "related_stakeholder", "related_property",
                  "related_loan", "related_investment", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes_text": forms.Textarea(attrs={"rows": 2}),
            "category": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget.choices = [("", "---------")] + [
            (v, l) for v, l in get_choices("cashflow_category")
        ]


class InlineCashFlowForm(TailwindFormMixin, forms.ModelForm):
    """Compact form for HTMX inline add on detail pages."""
    class Meta:
        model = CashFlowEntry
        fields = ["description", "amount", "entry_type", "category", "date", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes_text": forms.Textarea(attrs={"rows": 1}),
            "category": forms.Select(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget.choices = [("", "---------")] + [
            (v, l) for v, l in get_choices("cashflow_category")
        ]
