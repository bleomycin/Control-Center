from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


def check_overdue_tasks():
    """Daily: email listing all overdue tasks."""
    from tasks.models import Task

    today = timezone.localdate()
    overdue = Task.objects.filter(
        due_date__lt=today,
    ).exclude(
        status="complete",
    ).select_related("related_stakeholder")

    if not overdue.exists():
        return "No overdue tasks."

    lines = []
    for task in overdue:
        days = (today - task.due_date).days
        stakeholder = f" ({task.related_stakeholder.name})" if task.related_stakeholder else ""
        lines.append(f"  - {task.title}{stakeholder} — {days} day(s) overdue")

    body = f"You have {overdue.count()} overdue task(s):\n\n" + "\n".join(lines)

    send_mail(
        subject=f"[Control Center] {overdue.count()} Overdue Task(s)",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.ADMIN_EMAIL],
    )
    return f"Sent overdue alert for {overdue.count()} task(s)."


def check_upcoming_reminders():
    """Hourly: email for tasks with reminder_date in the next 24 hours."""
    from tasks.models import Task

    now = timezone.now()
    upcoming = Task.objects.filter(
        reminder_date__gte=now,
        reminder_date__lte=now + timedelta(hours=24),
    ).exclude(
        status="complete",
    ).select_related("related_stakeholder")

    if not upcoming.exists():
        return "No upcoming reminders."

    lines = []
    for task in upcoming:
        stakeholder = f" ({task.related_stakeholder.name})" if task.related_stakeholder else ""
        lines.append(f"  - {task.title}{stakeholder} — reminder at {task.reminder_date:%Y-%m-%d %H:%M}")

    body = f"Upcoming reminders ({upcoming.count()}):\n\n" + "\n".join(lines)

    send_mail(
        subject=f"[Control Center] {upcoming.count()} Upcoming Reminder(s)",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.ADMIN_EMAIL],
    )
    return f"Sent reminder alert for {upcoming.count()} task(s)."


def check_stale_followups():
    """Daily: email for follow-ups with no response received >3 days."""
    from tasks.models import FollowUp

    now = timezone.now()
    stale = FollowUp.objects.filter(
        response_received=False,
        outreach_date__lt=now - timedelta(days=3),
    ).select_related("task", "stakeholder")

    if not stale.exists():
        return "No stale follow-ups."

    lines = []
    for fu in stale:
        days = (now - fu.outreach_date).days
        lines.append(
            f"  - {fu.stakeholder.name} re: {fu.task.title} "
            f"({fu.get_method_display()}, {days} day(s) ago)"
        )

    body = f"You have {stale.count()} stale follow-up(s) with no response:\n\n" + "\n".join(lines)

    send_mail(
        subject=f"[Control Center] {stale.count()} Stale Follow-up(s)",
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[settings.ADMIN_EMAIL],
    )
    return f"Sent stale follow-up alert for {stale.count()} item(s)."
