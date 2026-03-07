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


def check_legal_followups():
    """Daily: notify about overdue legal communication follow-ups."""
    ctx = _get_email_context()
    if ctx is None:
        return "Notifications disabled."

    from legal.models import LegalCommunication

    today = timezone.localdate()
    overdue = LegalCommunication.objects.filter(
        follow_up_needed=True,
        follow_up_completed=False,
        follow_up_date__lt=today,
    ).select_related("stakeholder", "legal_matter")

    if not overdue.exists():
        return "No overdue legal follow-ups."

    lines = []
    for comm in overdue:
        days = (today - comm.follow_up_date).days
        contact = comm.stakeholder.name if comm.stakeholder else "Unknown"
        subject = f" — {comm.subject}" if comm.subject else ""
        lines.append(
            f"  - {comm.legal_matter.title}: {contact}{subject} "
            f"({days} day(s) overdue)"
        )

    body = (
        f"You have {overdue.count()} overdue legal follow-up(s):\n\n"
        + "\n".join(lines)
    )

    send_mail(
        subject=f"[Control Center] {overdue.count()} Overdue Legal Follow-up(s)",
        message=body,
        from_email=ctx["from_email"],
        recipient_list=[ctx["admin_email"]],
        connection=ctx["connection"],
    )

    from dashboard.models import Notification
    for comm in overdue:
        contact = comm.stakeholder.name if comm.stakeholder else "Unknown"
        Notification.objects.create(
            message=f"Overdue legal follow-up: {contact} re: {comm.legal_matter.title}",
            level="warning",
            link=comm.legal_matter.get_absolute_url(),
        )

    return f"Sent alert for {overdue.count()} overdue legal follow-up(s)."
