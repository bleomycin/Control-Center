from django.apps import AppConfig


class EmailLinksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "email_links"
    verbose_name = "Email Links"

    def ready(self):
        from .signals import connect_signals
        connect_signals()
