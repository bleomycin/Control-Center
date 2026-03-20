from django import forms

from config.forms import TailwindFormMixin

from .models import AssistantSettings


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
        help_text="Your Anthropic API key. Leave blank to use the ANTHROPIC_API_KEY environment variable.",
    )

    class Meta:
        model = AssistantSettings
        fields = ["api_key", "model", "max_tokens", "temperature"]
        widgets = {
            "max_tokens": forms.NumberInput(attrs={"min": 256, "max": 16384, "step": 256}),
            "temperature": forms.NumberInput(attrs={"min": 0, "max": 2, "step": 0.1}),
        }
