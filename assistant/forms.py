import re

from django import forms

from config.forms import TailwindFormMixin

from .models import AssistantSettings

# Anthropic model ids: "claude-" followed by lowercase alphanumerics/hyphens
# (aliases like claude-sonnet-4-6 and dated ids like
# claude-haiku-4-5-20251001 both match). A typo'd or non-Anthropic id used to
# save fine and then fail every send as a confusing request-time 404.
_MODEL_ID_RE = re.compile(r"^claude-[a-z0-9][a-z0-9-]*$")


class ChatInputForm(TailwindFormMixin, forms.Form):
    message = forms.CharField(
        widget=forms.Textarea(attrs={
            "rows": 1,
            "placeholder": "Ask anything about your data...",
            "autofocus": True,
        }),
    )


class AssistantSettingsForm(TailwindFormMixin, forms.ModelForm):
    model = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={
            "list": "model-choices",
            "placeholder": "claude-sonnet-4-6",
        }),
        help_text="Select a model or type a custom model ID.",
    )
    api_key = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": "sk-ant-..."}),
        help_text="Your Anthropic API key. Leave blank to keep the current key (or use the ANTHROPIC_API_KEY environment variable).",
    )

    def clean_api_key(self):
        """Preserve existing key when the password field is submitted empty."""
        key = self.cleaned_data.get("api_key", "")
        if not key and self.instance and self.instance.pk:
            return self.instance.api_key
        return key

    def clean_model(self):
        """Reject ids that can't be an Anthropic model at save time."""
        model = (self.cleaned_data.get("model") or "").strip()
        if not _MODEL_ID_RE.match(model):
            raise forms.ValidationError(
                "That doesn't look like an Anthropic model ID — expected "
                "something like 'claude-sonnet-4-6'. Pick one from the list "
                "or check the ID."
            )
        return model

    class Meta:
        model = AssistantSettings
        fields = ["owner_name", "api_key", "model", "max_tokens", "temperature", "default_reminder_minutes"]
        widgets = {
            "max_tokens": forms.NumberInput(attrs={"min": 256, "max": 16384, "step": 256}),
            "temperature": forms.NumberInput(attrs={"min": 0, "max": 2, "step": 0.1}),
            "default_reminder_minutes": forms.NumberInput(attrs={"min": 0, "max": 10080, "step": 15}),
        }
