"""Email connection helpers that read SMTP config from the DB at runtime."""


def get_smtp_connection():
    """Return an SMTP backend configured from EmailSettings, or console backend if unconfigured."""
    from django.core.mail.backends.console import EmailBackend as ConsoleBackend
    from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

    from dashboard.models import EmailSettings

    cfg = EmailSettings.load()
    if not cfg.is_configured():
        return ConsoleBackend()

    return SMTPBackend(
        host=cfg.smtp_host,
        port=cfg.smtp_port,
        username=cfg.username,
        password=cfg.password,
        use_tls=cfg.use_tls,
        use_ssl=cfg.use_ssl,
        timeout=10,
    )


def get_notification_addresses():
    """Return (from_email, admin_email) tuple from DB settings."""
    from dashboard.models import EmailSettings

    cfg = EmailSettings.load()
    return (cfg.from_email, cfg.admin_email)


def notifications_are_enabled():
    """Return True only if notifications are enabled AND SMTP is configured."""
    from dashboard.models import EmailSettings

    cfg = EmailSettings.load()
    return cfg.notifications_enabled and cfg.is_configured()
