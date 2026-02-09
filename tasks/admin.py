from django.contrib import admin
from .models import Task, FollowUp


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    fields = ["stakeholder", "outreach_date", "method", "response_received", "response_date", "notes_text"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "status", "priority", "due_date", "task_type", "related_stakeholder", "related_legal_matter"]
    list_filter = ["status", "priority", "task_type"]
    search_fields = ["title", "description"]
    inlines = [FollowUpInline]


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ["task", "stakeholder", "outreach_date", "method", "response_received"]
    list_filter = ["method", "response_received"]
    search_fields = ["task__title", "stakeholder__name", "notes_text"]
