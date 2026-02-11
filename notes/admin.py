from django.contrib import admin
from .models import Note, Attachment, Folder, Link, Tag


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0
    fields = ["file", "description"]


class LinkInline(admin.TabularInline):
    model = Link
    extra = 0
    fields = ["url", "description"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["title", "note_type", "date", "is_pinned", "folder", "created_at"]
    list_filter = ["note_type", "is_pinned", "folder"]
    search_fields = ["title", "content"]
    filter_horizontal = ["participants", "related_stakeholders", "related_legal_matters", "related_properties", "related_tasks", "tags"]
    inlines = [AttachmentInline, LinkInline]


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ["description", "note", "uploaded_at"]
    search_fields = ["description", "note__title"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "color", "created_at"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "sort_order", "created_at"]
    search_fields = ["name"]
