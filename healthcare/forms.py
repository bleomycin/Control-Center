from django import forms
from config.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import (Advice, Appointment, Condition, HealthcareTab, Prescription,
                     Provider, Supplement, TestResult, Visit)

DURATION_CHOICES = [
    ("", "---------"),
    (15, "15 minutes"),
    (30, "30 minutes"),
    (45, "45 minutes"),
    (60, "1 hour"),
    (90, "1.5 hours"),
    (120, "2 hours"),
    (180, "3 hours"),
    (240, "4 hours"),
]


class HealthcareTabForm(TailwindFormMixin, forms.Form):
    label = forms.CharField(max_length=100)
    healthcare_types = forms.MultipleChoiceField(
        choices=HealthcareTab.HEALTHCARE_TYPE_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Select at least one healthcare type."},
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        if instance:
            kwargs.setdefault("initial", {})
            kwargs["initial"]["label"] = instance.label
            kwargs["initial"]["healthcare_types"] = instance.healthcare_types
        super().__init__(*args, **kwargs)

    def save(self):
        if self.instance:
            self.instance.label = self.cleaned_data["label"]
            self.instance.healthcare_types = self.cleaned_data["healthcare_types"]
            self.instance.save()
            return self.instance
        tab = HealthcareTab(
            label=self.cleaned_data["label"],
            healthcare_types=self.cleaned_data["healthcare_types"],
        )
        last = HealthcareTab.objects.order_by("-sort_order").first()
        tab.sort_order = (last.sort_order + 1) if last else 0
        tab.save()
        return tab


class ProviderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Provider
        fields = ["name", "provider_type", "specialty", "practice_name",
                  "npi", "license_number", "phone", "fax", "email", "address",
                  "status", "stakeholder", "health_insurance", "notes_text"]
        widgets = {
            "provider_type": forms.Select(),
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["provider_type"].widget.choices = get_choices("provider_type")


class ConditionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Condition
        fields = ["name", "icd_code", "diagnosed_date", "status", "severity",
                  "diagnosed_by", "description", "treatment_plan", "notes_text"]
        widgets = {
            "diagnosed_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 3}),
            "treatment_plan": forms.Textarea(attrs={"rows": 3}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class PrescriptionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["medication_name", "generic_name", "dosage", "frequency", "route",
                  "pharmacy", "pharmacy_phone", "rx_number",
                  "start_date", "end_date", "refills_total", "refills_remaining",
                  "next_refill_date", "is_controlled", "purpose", "side_effects",
                  "status", "prescribing_provider", "related_condition",
                  "health_insurance", "notes_text"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "next_refill_date": forms.DateInput(attrs={"type": "date"}),
            "purpose": forms.Textarea(attrs={"rows": 2}),
            "side_effects": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class SupplementForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Supplement
        fields = ["name", "brand", "dosage", "frequency", "purpose",
                  "start_date", "end_date", "status", "recommended_by",
                  "related_condition", "notes_text"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "purpose": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class TestResultForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = TestResult
        fields = ["test_name", "test_type", "date", "facility",
                  "result_value", "reference_range", "unit", "status",
                  "result_summary", "file", "ordering_provider",
                  "related_condition", "health_insurance", "notes_text"]
        widgets = {
            "test_type": forms.Select(),
            "date": forms.DateInput(attrs={"type": "date"}),
            "result_summary": forms.Textarea(attrs={"rows": 3}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["test_type"].widget.choices = get_choices("test_type")


class VisitForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Visit
        fields = ["date", "time", "provider", "facility", "visit_type",
                  "reason", "diagnosis", "summary", "vitals",
                  "follow_up_instructions", "next_visit_date", "copay",
                  "related_condition", "health_insurance", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "next_visit_date": forms.DateInput(attrs={"type": "date"}),
            "diagnosis": forms.Textarea(attrs={"rows": 2}),
            "summary": forms.Textarea(attrs={"rows": 3}),
            "vitals": forms.Textarea(attrs={"rows": 2}),
            "follow_up_instructions": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class AdviceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Advice
        fields = ["title", "advice_text", "category", "date", "status",
                  "given_by", "related_visit", "related_condition", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "advice_text": forms.Textarea(attrs={"rows": 4}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }


class AppointmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ["title", "date", "time", "duration_minutes", "provider",
                  "facility", "address", "url", "visit_type", "purpose",
                  "preparation", "status", "related_condition",
                  "health_insurance", "notes_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "duration_minutes": forms.Select(choices=DURATION_CHOICES),
            "address": forms.Textarea(attrs={"rows": 2}),
            "purpose": forms.Textarea(attrs={"rows": 2}),
            "preparation": forms.Textarea(attrs={"rows": 2}),
            "notes_text": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "duration_minutes": "Duration",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            initial_date = self.initial.get("date")
            if initial_date:
                self.fields["date"].initial = initial_date
            initial_time = self.initial.get("time")
            if initial_time:
                self.fields["time"].initial = initial_time


class PrescriptionLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Prescription")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Prescription.objects.all()


class SupplementLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Supplement")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Supplement.objects.all()


class TestResultLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Test Result")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = TestResult.objects.all()


class VisitLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Visit")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Visit.objects.all()


class AppointmentLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Appointment")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Appointment.objects.all()


class ConditionLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Condition")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Condition.objects.all()


class AdviceLinkForm(TailwindFormMixin, forms.Form):
    item = forms.ModelChoiceField(queryset=None, label="Advice")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Advice.objects.all()


class HealthcareNoteLinkForm(TailwindFormMixin, forms.Form):
    note = forms.ModelChoiceField(
        queryset=None,
        label="Note",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from notes.models import Note
        self.fields["note"].queryset = Note.objects.all()


class HealthcareLegalLinkForm(TailwindFormMixin, forms.Form):
    legal_matter = forms.ModelChoiceField(
        queryset=None,
        label="Legal Matter",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from legal.models import LegalMatter
        self.fields["legal_matter"].queryset = LegalMatter.objects.all()
