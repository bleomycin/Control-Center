from django.contrib import admin

from .models import EmailSettings


@admin.register(EmailSettings)
class EmailSettingsAdmin(admin.ModelAdmin):
    list_display = ("__str__", "smtp_host", "notifications_enabled")

    def has_add_permission(self, request):
        # Only allow one instance
        return not EmailSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
