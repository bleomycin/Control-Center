"""Register Django-Q2 scheduled tasks for notifications."""
from django.core.management.base import BaseCommand
from django_q.models import Schedule


class Command(BaseCommand):
    help = "Register scheduled notification tasks in Django-Q2"

    def handle(self, *args, **options):
        schedules = [
            {
                "name": "Check Overdue Tasks",
                "func": "tasks.notifications.check_overdue_tasks",
                "schedule_type": Schedule.DAILY,
                "minutes": 0,
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
                "minutes": 0,
            },
        ]

        for sched in schedules:
            obj, created = Schedule.objects.update_or_create(
                name=sched["name"],
                defaults={
                    "func": sched["func"],
                    "schedule_type": sched["schedule_type"],
                },
            )
            action = "Created" if created else "Updated"
            self.stdout.write(f"  {action}: {sched['name']}")

        self.stdout.write(self.style.SUCCESS(
            f"\n{len(schedules)} schedule(s) registered. "
            "Run 'python manage.py qcluster' to start the worker."
        ))
