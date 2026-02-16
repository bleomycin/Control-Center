import re

from django import forms
from django.core.exceptions import ValidationError

from config.forms import TailwindFormMixin
from dashboard.models import BackupSettings, ChoiceOption, EmailSettings


class EmailSettingsForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = EmailSettings
        fields = [
            "smtp_host",
            "smtp_port",
            "use_tls",
            "use_ssl",
            "username",
            "password",
            "from_email",
            "admin_email",
            "notifications_enabled",
        ]
        widgets = {
            "password": forms.PasswordInput(attrs={"autocomplete": "off"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Show placeholder instead of actual password value
        if self.instance and self.instance.password:
            self.fields["password"].widget.attrs["placeholder"] = "Leave blank to keep current password"
        self.fields["password"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("use_tls") and cleaned.get("use_ssl"):
            raise ValidationError("TLS and SSL are mutually exclusive. Enable only one.")
        return cleaned

    def clean_password(self):
        password = self.cleaned_data.get("password")
        # Preserve existing password when field is left blank
        if not password and self.instance:
            return self.instance.password
        return password


class BackupSettingsForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = BackupSettings
        fields = ["enabled", "frequency", "time_hour", "time_minute", "retention_count"]

    def clean_time_hour(self):
        hour = self.cleaned_data.get("time_hour")
        if hour is not None and not (0 <= hour <= 23):
            raise ValidationError("Hour must be between 0 and 23.")
        return hour

    def clean_time_minute(self):
        minute = self.cleaned_data.get("time_minute")
        if minute is not None and not (0 <= minute <= 59):
            raise ValidationError("Minute must be between 0 and 59.")
        return minute


class ChoiceOptionForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = ChoiceOption
        fields = ["label", "value"]

    def __init__(self, *args, category=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.category = category or (self.instance.category if self.instance.pk else None)
        if not self.instance.pk:
            # For new options, auto-generate value from label
            self.fields["value"].required = False
            self.fields["value"].widget = forms.HiddenInput()

    def clean_value(self):
        value = self.cleaned_data.get("value")
        if not value:
            # Auto-generate from label
            label = self.cleaned_data.get("label", "")
            value = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if len(value) > 30:
            raise ValidationError("Value must be 30 characters or fewer.")
        return value

    def clean(self):
        cleaned = super().clean()
        value = cleaned.get("value")
        if value and self.category:
            qs = ChoiceOption.objects.filter(category=self.category, value=value)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(f"A choice with value '{value}' already exists in this category.")
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.category:
            instance.category = self.category
        if not instance.sort_order:
            max_order = ChoiceOption.objects.filter(
                category=instance.category,
            ).order_by("-sort_order").values_list("sort_order", flat=True).first()
            instance.sort_order = (max_order or 0) + 1
        if commit:
            instance.save()
        return instance
