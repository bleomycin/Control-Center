from django.contrib import admin

from .models import Checklist, ChecklistItem


class ChecklistItemInline(admin.TabularInline):
    model = ChecklistItem
    extra = 0


@admin.register(Checklist)
class ChecklistAdmin(admin.ModelAdmin):
    list_display = ["name", "due_date", "related_stakeholder", "related_task",
                    "related_property", "related_legal_matter", "created_at"]
    list_filter = ["due_date"]
    search_fields = ["name"]
    inlines = [ChecklistItemInline]
