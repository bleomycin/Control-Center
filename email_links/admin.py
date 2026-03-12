from django.contrib import admin
from .models import EmailLink


@admin.register(EmailLink)
class EmailLinkAdmin(admin.ModelAdmin):
    list_display = ["subject", "from_email", "date", "provider", "created_at"]
    list_filter = ["provider"]
    search_fields = ["subject", "from_name", "from_email", "message_id"]
    readonly_fields = ["created_at"]
