from django.contrib import admin
from .models import CashFlowEntry


@admin.register(CashFlowEntry)
class CashFlowEntryAdmin(admin.ModelAdmin):
    list_display = ["description", "amount", "entry_type", "category", "date", "is_projected"]
    list_filter = ["entry_type", "category", "is_projected"]
    search_fields = ["description", "category", "notes_text"]
