from django import forms
from django.core.exceptions import ValidationError

from blaine.forms import TailwindFormMixin
from dashboard.models import EmailSettings


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
