from django.contrib import admin
from .models import Task, FollowUp


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    fields = ["stakeholder", "outreach_date", "method", "reminder_enabled", "follow_up_days", "response_received", "response_date", "notes_text"]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["title", "direction", "status", "priority", "due_date", "due_time", "task_type", "related_legal_matter"]
    list_filter = ["status", "priority", "task_type", "direction"]
    search_fields = ["title", "description"]
    filter_horizontal = ["related_stakeholders"]
    inlines = [FollowUpInline]


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ["task", "stakeholder", "outreach_date", "method", "reminder_enabled", "follow_up_days", "response_received"]
    list_filter = ["method", "response_received", "reminder_enabled"]
    search_fields = ["task__title", "stakeholder__name", "notes_text"]
