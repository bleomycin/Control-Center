from django.contrib import admin
from .models import Document, GoogleDriveSettings


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "category", "date", "expiration_date", "has_drive_link", "created_at"]
    list_filter = ["category"]
    search_fields = ["title", "description", "gdrive_file_name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(GoogleDriveSettings)
class GoogleDriveSettingsAdmin(admin.ModelAdmin):
    list_display = ["__str__", "is_connected", "connected_email"]
