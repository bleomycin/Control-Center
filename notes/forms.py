from django import forms
from legacy.forms import TailwindFormMixin
from dashboard.choices import get_choices
from .models import Attachment, Folder, Link, Note, Tag


class TagForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Tag
        fields = ["name", "color"]


class FolderForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Folder
        fields = ["name", "color"]


class NoteForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Note
        fields = ["title", "content", "date", "note_type", "folder", "tags",
                  "participants", "related_stakeholders", "related_legal_matters",
                  "related_properties", "related_investments", "related_loans",
                  "related_tasks", "related_policies"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "content": forms.Textarea(attrs={"rows": 6}),
            "participants": forms.SelectMultiple(attrs={"size": 4}),
            "related_stakeholders": forms.SelectMultiple(attrs={"size": 4}),
            "related_legal_matters": forms.SelectMultiple(attrs={"size": 4}),
            "related_properties": forms.SelectMultiple(attrs={"size": 4}),
            "related_investments": forms.SelectMultiple(attrs={"size": 4}),
            "related_loans": forms.SelectMultiple(attrs={"size": 4}),
            "related_tasks": forms.SelectMultiple(attrs={"size": 4}),
            "related_policies": forms.SelectMultiple(attrs={"size": 4}),
            "tags": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note_type"].widget = forms.Select(choices=get_choices("note_type"))


class QuickNoteForm(TailwindFormMixin, forms.ModelForm):
    """Simplified form for quick capture modal."""
    stakeholder = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="- Stakeholder (optional) -",
    )
    task = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="- Task (optional) -",
    )

    class Meta:
        model = Note
        fields = ["title", "content", "date", "note_type", "folder", "tags"]
        widgets = {
            "date": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "content": forms.Textarea(attrs={"rows": 4}),
            "tags": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note_type"].widget = forms.Select(choices=get_choices("note_type"))
        from stakeholders.models import Stakeholder
        from tasks.models import Task
        self.fields["stakeholder"].queryset = Stakeholder.objects.all().order_by("name")
        self.fields["task"].queryset = Task.objects.exclude(status="complete").order_by("-created_at")

    def save(self, commit=True):
        note = super().save(commit=commit)
        if commit:
            stakeholder = self.cleaned_data.get("stakeholder")
            if stakeholder:
                note.participants.add(stakeholder)
            task = self.cleaned_data.get("task")
            if task:
                note.related_tasks.add(task)
        return note


class AttachmentForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ["file", "description"]


class LinkForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = Link
        fields = ["url", "description"]
        widgets = {
            "url": forms.URLInput(attrs={"placeholder": "https://docs.google.com/..."}),
            "description": forms.TextInput(attrs={"placeholder": "Q4 Financial Report"}),
        }
