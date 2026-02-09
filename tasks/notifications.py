from datetime import timedelta

from django.core.mail import send_mail
from django.utils import timezone


def _get_email_context():
    """Return email context dict or None if notifications are disabled."""
    from dashboard.email import (
        get_notification_addresses,
        get_smtp_connection,
        notifications_are_enabled,
    )

    if not notifications_are_enabled():
        return None

    from_email, admin_email = get_notification_addresses()
    return {
        "connection": get_smtp_connection(),
        "from_email": from_email,
        "admin_email": admin_email,
    }


def check_overdue_tasks():
    """Daily: email listing all overdue tasks."""
    ctx = _get_email_context()
    if ctx is None:
        return "Notifications disabled."

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
        from_email=ctx["from_email"],
        recipient_list=[ctx["admin_email"]],
        connection=ctx["connection"],
    )

    from dashboard.models import Notification
    for task in overdue:
        Notification.objects.create(
            message=f"Overdue: {task.title} ({(today - task.due_date).days} days)",
            level="warning",
            link=task.get_absolute_url(),
        )

    return f"Sent overdue alert for {overdue.count()} task(s)."


def check_upcoming_reminders():
    """Hourly: email for tasks with reminder_date in the next 24 hours."""
    ctx = _get_email_context()
    if ctx is None:
        return "Notifications disabled."

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
        from_email=ctx["from_email"],
        recipient_list=[ctx["admin_email"]],
        connection=ctx["connection"],
    )

    from dashboard.models import Notification
    for task in upcoming:
        Notification.objects.create(
            message=f"Reminder: {task.title}",
            level="info",
            link=task.get_absolute_url(),
        )

    return f"Sent reminder alert for {upcoming.count()} task(s)."


def check_stale_followups():
    """Daily: email for follow-ups with no response received >3 days."""
    ctx = _get_email_context()
    if ctx is None:
        return "Notifications disabled."

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
        from_email=ctx["from_email"],
        recipient_list=[ctx["admin_email"]],
        connection=ctx["connection"],
    )

    from dashboard.models import Notification
    for fu in stale:
        Notification.objects.create(
            message=f"Stale follow-up: {fu.stakeholder.name} re: {fu.task.title}",
            level="warning",
            link=fu.get_absolute_url(),
        )

    return f"Sent stale follow-up alert for {stale.count()} item(s)."
