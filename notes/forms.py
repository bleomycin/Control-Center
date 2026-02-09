from django import forms
from blaine.forms import TailwindFormMixin
from .models import Attachment, Note


class NoteForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Note
        fields = ["title", "content", "date", "note_type", "participants",
                  "related_stakeholders", "related_legal_matters",
                  "related_properties", "related_tasks"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "content": forms.Textarea(attrs={"rows": 6}),
            "participants": forms.SelectMultiple(attrs={"size": 4}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": 4}),
            "related_legal_matters": forms.SelectMultiple(attrs={"size": 4}),
            "related_properties": forms.SelectMultiple(attrs={"size": 4}),
            "related_tasks": forms.SelectMultiple(attrs={"size": 4}),
        }


class QuickNoteForm(TailwindFormMixin, forms.ModelForm):
    """Simplified form for quick capture modal."""
    class Meta:
        model = Note
        fields = ["title", "content", "date", "note_type"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "content": forms.Textarea(attrs={"rows": 4}),
        }


class AttachmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file", "description"]
