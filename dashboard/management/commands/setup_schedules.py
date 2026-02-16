"""Register Django-Q2 scheduled tasks for notifications and backups."""
from django.conf import settings as django_settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django_q.models import Schedule


BACKUP_SCHEDULE_NAME = "Automated Backup"


class Command(BaseCommand):
    help = "Register scheduled notification and backup tasks in Django-Q2"

    def handle(self, *args, **options):
        # --- Notification schedules (hardcoded) ---
        notification_schedules = [
            {
                "name": "Check Overdue Tasks",
                "func": "tasks.notifications.check_overdue_tasks",
                "schedule_type": Schedule.DAILY,
            },
            {
                "name": "Check Upcoming Reminders",
                "func": "tasks.notifications.check_upcoming_reminders",
                "schedule_type": Schedule.HOURLY,
            },
            {
                "name": "Check Stale Follow-ups",
                "func": "tasks.notifications.check_stale_followups",
                "schedule_type": Schedule.DAILY,
            },
        ]

        for sched in notification_schedules:
            obj, created = Schedule.objects.update_or_create(
                name=sched["name"],
                defaults={
                    "func": sched["func"],
                    "schedule_type": sched["schedule_type"],
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action}: {sched['name']}")

        # --- Backup schedule (configurable via BackupSettings) ---
        self._sync_backup_schedule()

        self.stdout.write(self.style.SUCCESS(
            "\nSchedules registered. "
            "Run 'python manage.py qcluster' to start the worker."
        ))

    def _sync_backup_schedule(self):
        from dashboard.models import BackupSettings

        config = BackupSettings.load()

        if not config.enabled:
            deleted, _ = Schedule.objects.filter(name=BACKUP_SCHEDULE_NAME).delete()
            if deleted:
                self.stdout.write(f"  Removed: {BACKUP_SCHEDULE_NAME} (disabled)")
            else:
                self.stdout.write(f"  Skipped: {BACKUP_SCHEDULE_NAME} (disabled)")
            return

        freq_map = {
            "D": Schedule.DAILY,
            "H": Schedule.HOURLY,
            "W": Schedule.WEEKLY,
        }
        schedule_type = freq_map[config.frequency]

        # Compute next_run in project timezone
        tz = timezone.get_current_timezone()
        now = timezone.localtime(timezone.now(), tz)
        next_run = now.replace(
            hour=config.time_hour,
            minute=config.time_minute,
            second=0,
            microsecond=0,
        )
        if next_run <= now:
            from datetime import timedelta
            if config.frequency == "H":
                next_run += timedelta(hours=1)
            elif config.frequency == "W":
                next_run += timedelta(weeks=1)
            else:
                next_run += timedelta(days=1)

        obj, created = Schedule.objects.update_or_create(
            name=BACKUP_SCHEDULE_NAME,
            defaults={
                "func": "dashboard.backup_task.run_backup",
                "schedule_type": schedule_type,
                "next_run": next_run,
            },
        )
        action = "Created" if created else "Updated"
        freq_label = dict(BackupSettings.FREQUENCY_CHOICES).get(config.frequency)
        self.stdout.write(
            f"  {action}: {BACKUP_SCHEDULE_NAME} "
            f"({freq_label} at {config.time_hour:02d}:{config.time_minute:02d}, "
            f"keep {config.retention_count})"
        )
