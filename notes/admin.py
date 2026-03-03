from django.contrib import admin
from .models import Note, Attachment


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ["file", "description"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["title", "note_type", "date", "created_at"]
    list_filter = ["note_type"]
    search_fields = ["title", "content"]
    filter_horizontal = ["participants", "related_stakeholders", "related_legal_matters", "related_properties", "related_tasks"]
    inlines = [AttachmentInline]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["description", "note", "uploaded_at"]
    search_fields = ["description", "note__title"]
