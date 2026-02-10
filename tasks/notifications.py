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

    direction_prefix = {"outbound": "[OUTBOUND] ", "inbound": "[INBOUND] "}
    lines = []
    for task in overdue:
        days = (today - task.due_date).days
        stakeholder = f" ({task.related_stakeholder.name})" if task.related_stakeholder else ""
        prefix = direction_prefix.get(task.direction, "")
        lines.append(f"  - {prefix}{task.title}{stakeholder} — {days} day(s) overdue")

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
        prefix = direction_prefix.get(task.direction, "")
        Notification.objects.create(
            message=f"Overdue: {prefix}{task.title} ({(today - task.due_date).days} days)",
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
    """Daily: email for follow-ups past their per-follow-up reminder window."""
    ctx = _get_email_context()
    if ctx is None:
        return "Notifications disabled."

    from tasks.models import FollowUp

    now = timezone.now()
    pending = FollowUp.objects.filter(
        response_received=False,
        reminder_enabled=True,
    ).exclude(
        task__status="complete",
    ).select_related("task", "stakeholder")

    stale = [fu for fu in pending if fu.is_stale]

    if not stale:
        return "No stale follow-ups."

    from dashboard.choices import get_choice_label

    lines = []
    for fu in stale:
        days = (now - fu.outreach_date).days
        lines.append(
            f"  - {fu.stakeholder.name} re: {fu.task.title} "
            f"({get_choice_label('contact_method', fu.method)}, {days} day(s) ago, "
            f"remind after {fu.follow_up_days})"
        )

    body = f"You have {len(stale)} stale follow-up(s) with no response:\n\n" + "\n".join(lines)

    send_mail(
        subject=f"[Control Center] {len(stale)} Stale Follow-up(s)",
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

    return f"Sent stale follow-up alert for {len(stale)} item(s)."
