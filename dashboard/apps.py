from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = 'dashboard'

    # SQLite pragmas (WAL, busy_timeout, synchronous, cache_size) used to be
    # applied here via a connection_created signal. They now live in
    # settings.DATABASES OPTIONS (init_command) so there is exactly one
    # source of truth — the signal fired AFTER init_command and silently
    # overrode its busy_timeout with a conflicting value (Phase 6 Defect B).
