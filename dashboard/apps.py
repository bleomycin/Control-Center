from django.apps import AppConfig


class DashboardConfig(AppConfig):
    name = 'dashboard'

    def ready(self):
        from django.db.backends.signals import connection_created

        def set_sqlite_pragmas(sender, connection, **kwargs):
            if connection.vendor == 'sqlite':
                cursor = connection.cursor()
                cursor.execute('PRAGMA journal_mode=WAL;')
                cursor.execute('PRAGMA synchronous=NORMAL;')
                # Wait up to 15s for a write lock before raising "database is
                # locked". The web app, the django-q2 qcluster, and the
                # assistant stream worker all write to the same SQLite file.
                cursor.execute('PRAGMA busy_timeout=15000;')
                cursor.execute('PRAGMA cache_size=-20000;')
                cursor.execute('PRAGMA foreign_keys=ON;')

        connection_created.connect(set_sqlite_pragmas, weak=False)
